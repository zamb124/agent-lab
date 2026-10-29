import uuid
from datetime import UTC, date, datetime

from apps.crm.models.api import EntityMergeRequest, MergeSide
from apps.crm.models.crm_entity import CRMEntity
from apps.crm.models.entity_type import EntityType
from apps.crm.models.suggest import CRMSuggest
from apps.crm.services.entity_service import EntityService
from apps.crm.services.note_processing_service import NoteProcessingService
from core.context import require_active_company
from core.pagination import OffsetPage
from core.rag import BaseRAGProvider
from core.rag.post_retrieval_rerank import RerankScoreCache
from core.types import JsonObject, require_json_object

_DUPLICATE_SIMILARITY_THRESHOLD = 0.85
_SUGGEST_SCAN_LIMIT = 50
_SUGGEST_MERGE_SCALAR_KEYS: tuple[str, ...] = (
    "name",
    "description",
    "status",
    "entity_subtype",
    "note_date",
)
_SKIP_DUPLICATE_STATUSES = {"pending", "dismissed"}


class SuggestService:
    def __init__(
        self,
        entity_service: EntityService,
        note_processing_service: NoteProcessingService,
        rag: BaseRAGProvider,
        rerank_score_cache: RerankScoreCache,
    ) -> None:
        self._entity_service: EntityService = entity_service
        self._note_processing_service: NoteProcessingService = note_processing_service
        self._rag: BaseRAGProvider = rag
        self._rerank_score_cache: RerankScoreCache = rerank_score_cache

    async def list_suggests_by_created_at_desc(
        self,
        namespace: str,
        status: str | None = "pending",
        limit: int = 50,
        offset: int = 0,
    ) -> OffsetPage[CRMSuggest]:
        """Страница подсказок, ORDER BY created_at DESC. Пустой status не фильтрует."""
        rows = CRMSuggest.query_in_company_namespace(self._company_id(), namespace)
        if status is not None and status != "":
            rows = rows.filter(status=status)
        total = await rows.count()
        items = await rows.order_by("-created_at").limit(limit).offset(offset).all()
        return OffsetPage[CRMSuggest](items=items, total=total, limit=limit, offset=offset)

    async def get_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest | None:
        return await CRMSuggest.query_in_company_namespace(
            self._company_id(), namespace
        ).filter(suggest_id=suggest_id).get_or_none()

    async def resolve_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest:
        suggest = await self.get_suggest(suggest_id, namespace=namespace)
        if suggest is None:
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
            draft_raw = note.attributes.get("ai_analysis_draft")
            if draft_raw is None:
                raise ValueError("missed_entity suggest draft version is stale")
            draft = require_json_object(draft_raw, "ai_analysis_draft")
            if draft.get("draft_version") != expected_draft_version:
                raise ValueError("missed_entity suggest draft version is stale")
            _ = await self._note_processing_service.apply(note_id)
        else:
            raise ValueError(f"Unknown suggest type {suggest.suggest_type}")

        return await self._set_status(suggest, "resolved")

    async def dismiss_suggest(self, suggest_id: str, *, namespace: str) -> CRMSuggest:
        suggest = await self.get_suggest(suggest_id, namespace=namespace)
        if suggest is None:
            raise ValueError(f"Suggest {suggest_id} not found")

        if suggest.status != "pending":
            raise ValueError(f"Suggest {suggest_id} is already {suggest.status}")

        return await self._set_status(suggest, "dismissed")

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
        """
        Сканирует кандидатов-дубликатов и формирует CRMSuggest.

        Производительность: семантический поиск всё ещё делается на каждую
        scan-entity (вынести в batch RAG за пределами этой задачи), но lookup
        существующих suggests и entity_type — теперь по одному batched-запросу
        на весь scan. До правки на 50-entity scan уходило 550+ запросов
        (50 × (search + N × find_by_targets + N × get_by_type_id)); теперь —
        ~52 (50 search + 1 find_by_targets_batch + 1 get_by_type_ids).
        """
        page = await CRMEntity.cursor_page_by_created_at_and_entity_id_desc(
            namespace=namespace,
            limit=_SUGGEST_SCAN_LIMIT,
            company_id=company_id,
        )
        entities = page.items

        seen_pairs: set[tuple[str, str]] = set()
        pair_plan: list[tuple[CRMEntity, CRMEntity, tuple[str, str]]] = []
        for entity in entities:
            if entity.is_note:
                continue
            query = self._entity_search_query(entity)
            candidates = await self._entity_service.search_similar(
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
                pair_plan.append((entity, candidate, pair_key))
                break

        if not pair_plan:
            return {
                "duplicate_created": 0,
                "duplicate_auto_resolved": 0,
                "duplicate_skipped_existing": 0,
            }

        existing_suggests = await self._latest_by_targets(
            namespace=namespace,
            suggest_type="duplicate",
            target_entity_ids_batches=[list(pair_key) for _, _, pair_key in pair_plan],
            statuses=_SKIP_DUPLICATE_STATUSES,
        )

        entity_type_ids = sorted({entity.entity_type.strip() for entity, _, _ in pair_plan if entity.entity_type.strip()})
        if len(entity_type_ids) == 0:
            entity_types_by_id = {}
        else:
            entity_type_rows = await EntityType.query_by_namespace_in_company(
                company_id,
                namespace=namespace,
            ).filter(type_id__in=entity_type_ids).all()
            entity_types_by_id = {row.type_id: row for row in entity_type_rows}

        created_count = 0
        auto_resolved_count = 0
        skipped_existing_count = 0
        for entity, candidate, pair_key in pair_plan:
            target_entity_ids = list(pair_key)
            existing_key = tuple(sorted(target_entity_ids))
            if existing_suggests.get(existing_key) is not None:
                skipped_existing_count += 1
                continue

            entity_type = entity_types_by_id.get(entity.entity_type)
            if entity_type is None:
                raise ValueError(
                    f"EntityType {entity.entity_type!r} not found in namespace {namespace!r}"
                )

            merge_request = self._build_merge_request(entity, candidate)
            merge_payload = require_json_object(
                merge_request.model_dump(mode="json"), "EntityMergeRequest"
            )

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
        notes = await CRMEntity.list_notes_with_analysis_draft_not_applied_by_updated_at_and_entity_id_desc(
            namespace=namespace,
            limit=_SUGGEST_SCAN_LIMIT,
            company_id=company_id,
        )
        created_count = 0
        for note in notes:
            draft_raw = note.attributes.get("ai_analysis_draft")
            if draft_raw is None:
                raise ValueError(f"Note {note.entity_id} has invalid ai_analysis_draft")
            draft = require_json_object(draft_raw, "ai_analysis_draft")
            raw_draft_version = draft.get("draft_version")
            if not isinstance(raw_draft_version, int):
                raise ValueError(f"Note {note.entity_id} has invalid ai_analysis_draft")
            draft_version = raw_draft_version
            existing = await self._latest_for_targets(
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
        return await CRMSuggest.create(suggest)

    def _company_id(self) -> str:
        return require_active_company().company_id

    async def _set_status(self, suggest: CRMSuggest, status: str) -> CRMSuggest:
        updated_at = datetime.now(UTC)
        updated = await CRMSuggest.mark_status(suggest, status, updated_at)
        if updated != 1:
            raise ValueError("Failed to update suggest status")
        suggest.status = status
        suggest.updated_at = updated_at
        return suggest

    async def _latest_for_targets(
        self,
        *,
        namespace: str,
        suggest_type: str,
        target_entity_ids: list[str],
        statuses: set[str],
    ) -> CRMSuggest | None:
        normalized = self._normalized_targets(target_entity_ids)
        if len(statuses) == 0:
            raise ValueError("statuses are required")
        return await (
            CRMSuggest.query_in_company_namespace(self._company_id(), namespace)
            .filter(
                suggest_type=suggest_type,
                target_entity_ids=normalized,
                status__in=sorted(statuses),
            )
            .order_by("-created_at")
            .first()
        )

    async def _latest_by_targets(
        self,
        *,
        namespace: str,
        suggest_type: str,
        target_entity_ids_batches: list[list[str]],
        statuses: set[str],
    ) -> dict[tuple[str, ...], CRMSuggest]:
        if len(target_entity_ids_batches) == 0:
            return {}
        if len(statuses) == 0:
            raise ValueError("statuses are required")
        normalized_batches: list[list[str]] = []
        for batch in target_entity_ids_batches:
            normalized = sorted({item.strip() for item in batch if item.strip()})
            if len(normalized) == 0:
                continue
            normalized_batches.append(normalized)
        if len(normalized_batches) == 0:
            return {}
        rows = await (
            CRMSuggest.query_in_company_namespace(self._company_id(), namespace)
            .filter(
                suggest_type=suggest_type,
                target_entity_ids__in=normalized_batches,
                status__in=sorted(statuses),
            )
            .order_by("-created_at")
            .all()
        )
        latest: dict[tuple[str, ...], CRMSuggest] = {}
        for row in rows:
            key = tuple(row.target_entity_ids)
            if key not in latest:
                latest[key] = row
        return latest

    @staticmethod
    def _normalized_targets(target_entity_ids: list[str]) -> list[str]:
        normalized = sorted({item.strip() for item in target_entity_ids if item.strip()})
        if len(normalized) == 0:
            raise ValueError("target_entity_ids are required")
        return normalized

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
        if key == "note_date":
            return entity.note_date
        raise ValueError(f"Unsupported suggest merge scalar key: {key}")
