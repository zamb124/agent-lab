import uuid
from datetime import UTC, date, datetime

from apps.crm.db.models import CRMEntity, CRMSuggest
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.suggest_repository import CRMSuggestPage, SuggestRepository
from apps.crm.models.api import EntityMergeRequest, MergeSide
from apps.crm.services.entity_service import EntityService
from apps.crm.services.note_processing_service import NoteProcessingService
from apps.crm.types import JsonObject
from core.types import require_json_object

_DUPLICATE_SIMILARITY_THRESHOLD = 0.85
_SUGGEST_SCAN_LIMIT = 50
_SUGGEST_MERGE_SCALAR_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "status",
    "entity_subtype",
    "priority",
    "note_date",
    "due_date",
)
_SKIP_DUPLICATE_STATUSES = {"pending", "dismissed"}


class SuggestService:
    def __init__(
        self,
        repository: SuggestRepository,
        entity_service: EntityService,
        note_processing_service: NoteProcessingService,
        entity_repository: EntityRepository,
        entity_type_repository: EntityTypeRepository,
    ) -> None:
        self._repository: SuggestRepository = repository
        self._entity_service: EntityService = entity_service
        self._note_processing_service: NoteProcessingService = note_processing_service
        self._entity_repository: EntityRepository = entity_repository
        self._entity_type_repository: EntityTypeRepository = entity_type_repository

    @staticmethod
    def _as_json_object(value: object) -> JsonObject | None:
        try:
            return require_json_object(value, "suggest json object")
        except ValueError:
            return None

    async def list_suggests(
        self,
        namespace: str,
        status: str | None = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> CRMSuggestPage:
        return await self._repository.list_suggests(namespace, status, limit, offset)

    async def get_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest | None:
        return await self._repository.get(suggest_id, namespace=namespace)

    async def resolve_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest:
        suggest = await self._repository.get(suggest_id, namespace=namespace)
        if not suggest:
            raise ValueError(f"Suggest {suggest_id} not found")

        if suggest.status != "pending":
            raise ValueError(f"Suggest {suggest_id} is already {suggest.status}")

        if suggest.suggest_type == "duplicate":
            merge_req = EntityMergeRequest.model_validate(suggest.payload)
            _ = await self._entity_service.merge_entities(merge_req)
        elif suggest.suggest_type == "missed_entity":
            note_id = suggest.payload.get("note_id")
            if not isinstance(note_id, str) or not note_id.strip():
                raise ValueError("missed_entity suggest payload.note_id is required")
            if note_id not in suggest.target_entity_ids:
                raise ValueError("missed_entity suggest target_entity_ids must include note_id")
            expected_draft_version = suggest.payload.get("draft_version")
            if not isinstance(expected_draft_version, int):
                raise ValueError("missed_entity suggest payload.draft_version is required")
            note = await self._entity_service.get_entity(note_id)
            if note is None:
                raise ValueError(f"Note {note_id} not found")
            draft = self._as_json_object(note.attributes.get("ai_analysis_draft"))
            if draft is None or draft.get("draft_version") != expected_draft_version:
                raise ValueError("missed_entity suggest draft version is stale")
            _ = await self._note_processing_service.apply(note_id)
        else:
            raise ValueError(f"Unknown suggest type {suggest.suggest_type}")

        updated = await self._repository.update_status(suggest_id, "resolved", namespace=namespace)
        if not updated:
            raise ValueError("Failed to update suggest status")
        return updated

    async def dismiss_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest:
        suggest = await self._repository.get(suggest_id, namespace=namespace)
        if not suggest:
            raise ValueError(f"Suggest {suggest_id} not found")

        if suggest.status != "pending":
            raise ValueError(f"Suggest {suggest_id} is already {suggest.status}")

        updated = await self._repository.update_status(suggest_id, "dismissed", namespace=namespace)
        if not updated:
            raise ValueError("Failed to update suggest status")
        return updated

    async def generate_namespace_suggests(
        self,
        *,
        company_id: str,
        namespace: str,
    ) -> dict[str, int]:
        duplicate_counts = await self._generate_duplicate_suggests(
            company_id=company_id,
            namespace=namespace,
        )
        missed_entity_created = await self._generate_missed_entity_suggests(
            company_id=company_id,
            namespace=namespace,
        )
        return {
            **duplicate_counts,
            "missed_entity_created": missed_entity_created,
        }

    async def _generate_duplicate_suggests(
        self,
        *,
        company_id: str,
        namespace: str,
    ) -> dict[str, int]:
        entities, _, _ = await self._entity_repository.list_by_cursor(
            namespace=namespace,
            limit=_SUGGEST_SCAN_LIMIT,
            company_id=company_id,
        )
        seen_pairs: set[tuple[str, str]] = set()
        created_count = 0
        auto_resolved_count = 0
        skipped_existing_count = 0

        for entity in entities:
            if entity.is_note:
                continue
            query = self._entity_search_query(entity)
            candidates = await self._entity_repository.search_with_similarity(
                query=query,
                entity_type=entity.entity_type,
                namespace=namespace,
                limit=5,
                company_id=company_id,
            )
            for candidate, similarity in candidates:
                if candidate.entity_id == entity.entity_id or candidate.is_note:
                    continue
                pair_key = self._pair_key(entity.entity_id, candidate.entity_id)
                if pair_key in seen_pairs:
                    continue
                if similarity <= _DUPLICATE_SIMILARITY_THRESHOLD:
                    continue

                seen_pairs.add(pair_key)
                target_entity_ids = list(pair_key)
                existing = await self._repository.find_by_targets(
                    namespace=namespace,
                    suggest_type="duplicate",
                    target_entity_ids=target_entity_ids,
                    statuses=_SKIP_DUPLICATE_STATUSES,
                )
                if existing is not None:
                    skipped_existing_count += 1
                    continue

                entity_type = await self._entity_type_repository.get_by_type_id(
                    entity.entity_type,
                    namespace=namespace,
                    company_id=company_id,
                )
                if entity_type is None:
                    raise ValueError(
                        f"EntityType {entity.entity_type!r} not found in namespace {namespace!r}"
                    )

                merge_request = self._build_merge_request(entity, candidate)
                merge_payload = self._as_json_object(merge_request.model_dump(mode="json"))
                if merge_payload is None:
                    raise ValueError("EntityMergeRequest payload must be JSON object")
                if entity_type.auto_resolve_suggests:
                    _ = await self._entity_service.merge_entities(merge_request)
                    _ = await self._create_suggest(
                        company_id=company_id,
                        namespace=namespace,
                        suggest_type="duplicate",
                        status="auto_resolved",
                        target_entity_ids=target_entity_ids,
                        payload=merge_payload,
                    )
                    auto_resolved_count += 1
                else:
                    _ = await self._create_suggest(
                        company_id=company_id,
                        namespace=namespace,
                        suggest_type="duplicate",
                        status="pending",
                        target_entity_ids=target_entity_ids,
                        payload=merge_payload,
                    )
                    created_count += 1
                break

        return {
            "duplicate_created": created_count,
            "duplicate_auto_resolved": auto_resolved_count,
            "duplicate_skipped_existing": skipped_existing_count,
        }

    async def _generate_missed_entity_suggests(
        self,
        *,
        company_id: str,
        namespace: str,
    ) -> int:
        notes = await self._entity_repository.list_notes_with_analysis_draft_not_applied(
            namespace=namespace,
            limit=_SUGGEST_SCAN_LIMIT,
            company_id=company_id,
        )
        created_count = 0
        for note in notes:
            draft = self._as_json_object(note.attributes.get("ai_analysis_draft"))
            if draft is None:
                raise ValueError(f"Note {note.entity_id} has invalid ai_analysis_draft")
            raw_draft_version = draft.get("draft_version")
            if not isinstance(raw_draft_version, int):
                raise ValueError(f"Note {note.entity_id} has invalid ai_analysis_draft")
            draft_version = raw_draft_version
            existing = await self._repository.find_by_targets(
                namespace=namespace,
                suggest_type="missed_entity",
                target_entity_ids=[note.entity_id],
                statuses=_SKIP_DUPLICATE_STATUSES,
            )
            if existing is not None:
                if existing.status == "pending":
                    continue
                if existing.payload.get("draft_version") == draft_version:
                    continue
            _ = await self._create_suggest(
                company_id=company_id,
                namespace=namespace,
                suggest_type="missed_entity",
                status="pending",
                target_entity_ids=[note.entity_id],
                payload={"note_id": note.entity_id, "draft_version": draft_version},
            )
            created_count += 1
        return created_count

    async def _create_suggest(
        self,
        *,
        company_id: str,
        namespace: str,
        suggest_type: str,
        status: str,
        target_entity_ids: list[str],
        payload: JsonObject,
    ) -> CRMSuggest:
        now = datetime.now(UTC)
        suggest = CRMSuggest(
            suggest_id=f"sug_{uuid.uuid4().hex}",
            company_id=company_id,
            namespace=namespace,
            suggest_type=suggest_type,
            status=status,
            target_entity_ids=sorted(target_entity_ids),
            payload=payload,
            created_at=now,
            updated_at=now,
        )
        return await self._repository.create(suggest)

    @staticmethod
    def _entity_search_query(entity: CRMEntity) -> str:
        parts = [entity.name]
        if entity.description:
            parts.append(entity.description)
        return "\n".join(parts)

    @staticmethod
    def _pair_key(left_entity_id: str, right_entity_id: str) -> tuple[str, str]:
        left, right = sorted((left_entity_id, right_entity_id))
        return left, right

    @staticmethod
    def _build_merge_request(left: CRMEntity, right: CRMEntity) -> EntityMergeRequest:
        survivor, source = sorted(
            (left, right),
            key=lambda item: (item.created_at, item.entity_id),
        )
        scalar_choices: dict[str, MergeSide] = {}
        for key in _SUGGEST_MERGE_SCALAR_KEYS:
            survivor_value = SuggestService._merge_scalar_value(survivor, key)
            source_value = SuggestService._merge_scalar_value(source, key)
            if survivor_value != source_value:
                scalar_choices[key] = "survivor"

        survivor_attrs = dict(survivor.attributes or {})
        source_attrs = dict(source.attributes or {})
        attribute_choices: dict[str, MergeSide] = {}
        for key in sorted(set(survivor_attrs) & set(source_attrs)):
            if survivor_attrs[key] != source_attrs[key]:
                attribute_choices[key] = "survivor"

        return EntityMergeRequest(
            survivor_entity_id=survivor.entity_id,
            source_entity_id=source.entity_id,
            scalar_choices=scalar_choices,
            attribute_choices=attribute_choices,
        )

    @staticmethod
    def _merge_scalar_value(
        entity: CRMEntity, key: str
    ) -> str | int | float | date | datetime | None:
        if key == "name":
            return entity.name
        if key == "description":
            return entity.description
        if key == "status":
            return entity.status
        if key == "entity_subtype":
            return entity.entity_subtype
        if key == "priority":
            return entity.priority
        if key == "note_date":
            return entity.note_date
        if key == "due_date":
            return entity.due_date
        raise ValueError(f"Unsupported suggest merge scalar key: {key}")
