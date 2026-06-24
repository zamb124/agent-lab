"""
Интеграция AmoCRM: OAuth service key, импорт сущностей v4, справочник custom_fields.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from typing import cast

from apps.crm.constants_graph import BELONGS_TO_RELATIONSHIP_TYPE
from apps.crm.db.models import CRMEntity, Relationship
from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.crm.db.repositories.entity_type_repository import EntityTypeRepository
from apps.crm.db.repositories.relationship_repository import RelationshipRepository
from apps.crm.integrations.amocrm.mapping import (
    AMO_PROVIDER_ID,
    AMO_USERS_ENTITY_TYPE_ID,
    ENTITY_TYPE_BY_AMO_COLLECTION,
)
from apps.crm.integrations.entity_upsert import upsert_canonical_by_external_ref
from apps.crm.models.api import NoteProcessingConfig
from apps.crm.services.crm_work_item_service import CrmTaskWorkSeed
from apps.crm.services.entity_service import EntityService
from apps.crm.services.task_service import ActiveTaskExistsError, TaskService
from core.context import get_context
from core.db.repositories.namespace_repository import NamespaceRepository
from core.http.client import get_httpx_client
from core.identity.integration_external_author import IntegrationExternalAuthorService
from core.integrations.models import IntegrationProvider
from core.integrations.oauth_service import OAuthService, OAuthTokenRefreshError
from core.types import JsonObject

AMO_RPS_DELAY_SEC = 0.15
AMO_PROGRESS_BATCH = 500

AMO_USERS_PATH = "users"

RELATED_TO_RELATIONSHIP_TYPE = "related_to"
ASSIGNED_TO_RELATIONSHIP_TYPE = "assigned_to"

AMO_STANDARD_TASK_TYPE_NAMES: dict[int, str] = {
    1: "Звонок",
    2: "Встреча",
}

AmoProgressFn = Callable[[str, int], Awaitable[None]]
AmoItemMapper = Callable[[JsonObject, str, str, str, str, str], Awaitable[None]]


def _as_json_object(value: object) -> JsonObject | None:
    if isinstance(value, dict):
        return cast(JsonObject, value)
    return None


class AmoCRMIntegrationService:
    def __init__(
        self,
        oauth_service: OAuthService,
        entity_repository: EntityRepository,
        entity_type_repository: EntityTypeRepository,
        relationship_repository: RelationshipRepository,
        entity_service: EntityService,
        namespace_repository: NamespaceRepository,
        task_service: TaskService,
        integration_external_author: IntegrationExternalAuthorService,
    ) -> None:
        self._oauth: OAuthService = oauth_service
        self._entity_repo: EntityRepository = entity_repository
        self._entity_type_repo: EntityTypeRepository = entity_type_repository
        self._relationship_repo: RelationshipRepository = relationship_repository
        self._entity_service: EntityService = entity_service
        self._namespace_repo: NamespaceRepository = namespace_repository
        self._task_service: TaskService = task_service
        self._integration_author: IntegrationExternalAuthorService = integration_external_author

    def _service_key(self, namespace_name: str) -> str:
        return f"amocrm:{namespace_name}"

    async def _auto_note_ai_analyze_enabled(
        self,
        *,
        namespace: str,
        company_id: str,
    ) -> bool:
        existing = await self._namespace_repo.get(namespace)
        if existing is None or existing.company_id != company_id:
            return False
        crm = existing.crm_settings
        if crm is None:
            return False
        block = crm.integrations.get("amocrm")
        if not isinstance(block, dict):
            return False
        return bool(block.get("auto_note_ai_analyze"))

    def _api_base(self, subdomain: str) -> str:
        s = subdomain.strip().strip("/")
        if not s:
            raise ValueError("Пустой поддомен amo")
        return f"https://{s}.amocrm.ru"

    async def _get_token(
        self,
        *,
        company_id: str,
        user_id: str,
        namespace_name: str,
    ) -> tuple[str, str]:
        cred = await self._oauth.get_valid_token(
            company_id=company_id,
            user_id=user_id,
            provider=IntegrationProvider.AMOCRM,
            service=self._service_key(namespace_name),
        )
        if cred is None:
            raise ValueError("Интеграция AmoCRM не подключена для этого пространства")
        sub_raw = cred.metadata.get("amocrm_subdomain")
        if not isinstance(sub_raw, str) or not sub_raw.strip():
            raise ValueError("В credential нет amocrm_subdomain")
        access = cred.access_token
        if not access:
            raise ValueError("Пустой access_token AmoCRM")
        return access, sub_raw.strip()

    async def _get_json(
        self,
        url: str,
        access_token: str,
    ) -> JsonObject:
        async with get_httpx_client(timeout=60.0) as client:
            response = await client.get(
                url,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
            )
        if response.status_code == 429:
            raise RuntimeError("AmoCRM rate limit (429), повторите позже")
        _ = response.raise_for_status()
        if response.status_code == 204:
            return {}
        if not response.content.strip():
            return {}
        payload = cast(object, response.json())
        payload_obj = _as_json_object(payload)
        if payload_obj is None:
            raise ValueError("AmoCRM API returned non-object JSON")
        return payload_obj

    def _next_page_url(self, payload: JsonObject) -> str | None:
        links = payload.get("_links")
        links_obj = _as_json_object(links)
        if links_obj is None:
            return None
        nxt = links_obj.get("next")
        nxt_obj = _as_json_object(nxt)
        if nxt_obj is not None:
            href = nxt_obj.get("href")
            if isinstance(href, str) and href.strip():
                return href.strip()
        return None

    def _embedded_list(self, payload: JsonObject, key: str) -> list[JsonObject]:
        emb = payload.get("_embedded")
        emb_obj = _as_json_object(emb)
        if emb_obj is None:
            return []
        raw = emb_obj.get(key)
        if not isinstance(raw, list):
            return []
        out: list[JsonObject] = []
        for item in cast(list[object], raw):
            item_obj = _as_json_object(item)
            if item_obj is not None:
                out.append(item_obj)
        return out

    @staticmethod
    def _amo_ids_from_embedded_dict(emb: object, key: str) -> list[str]:
        emb_obj = _as_json_object(emb)
        if emb_obj is None:
            return []
        items = emb_obj.get(key)
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for item_raw in cast(list[object], items):
            item = _as_json_object(item_raw)
            if item is None:
                continue
            iid = item.get("id")
            if iid is None:
                continue
            s = str(iid).strip()
            if s:
                out.append(s)
        return out

    @staticmethod
    def _amo_ids_from_item_embedded(raw: JsonObject, key: str) -> list[str]:
        emb = raw.get("_embedded")
        return AmoCRMIntegrationService._amo_ids_from_embedded_dict(emb, key)

    async def _resolve_canonical_entity_id(
        self,
        *,
        company_id: str,
        namespace: str,
        entity_type: str,
        amo_record_id: str,
    ) -> str | None:
        rows = await self._entity_repo.find_by_external_ref(
            company_id=company_id,
            namespace=namespace,
            entity_type=entity_type,
            source_id=AMO_PROVIDER_ID,
            record_id=str(amo_record_id),
        )
        if len(rows) != 1:
            return None
        return rows[0].entity_id

    async def _ensure_relationship(
        self,
        *,
        namespace: str,
        company_id: str,
        source_entity_id: str,
        target_entity_id: str,
        relationship_type: str,
    ) -> bool:
        if source_entity_id == target_entity_id:
            return False
        existing = await self._relationship_repo.find_exact(
            source_entity_id,
            target_entity_id,
            relationship_type,
            namespace=namespace,
        )
        if existing is not None:
            return False
        rel = Relationship(
            relationship_id=uuid.uuid4().hex,
            company_id=company_id,
            namespace=namespace,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            weight=1.0,
            confidence=1.0,
            attributes={},
        )
        _ = await self._relationship_repo.create(rel)
        return True

    @staticmethod
    def _amo_note_plain_text(raw: JsonObject) -> str | None:
        t = raw.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
        params = raw.get("params")
        params_obj = _as_json_object(params)
        if params_obj is not None:
            pt = params_obj.get("text")
            if isinstance(pt, str) and pt.strip():
                return pt.strip()
        return None

    @staticmethod
    def _mention_token_visible_name(name: str) -> str:
        s = name.strip()
        if not s:
            return "entity"
        return s.replace("[", "(").replace("]", ")")

    @staticmethod
    def _amo_users_directory_from_api(users: list[object]) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for raw_item in users:
            raw = _as_json_object(raw_item)
            if raw is None:
                continue
            tid = raw.get("id")
            if tid is None:
                continue
            key = str(tid).strip()
            if not key:
                continue
            email_raw = raw.get("email")
            email = email_raw.strip().lower() if isinstance(email_raw, str) else ""
            name_raw = raw.get("name") or raw.get("title")
            name_str = str(name_raw).strip() if name_raw is not None else ""
            out[key] = {"email": email, "name": name_str}
        return out

    async def _platform_user_id_for_amo_author(
        self,
        *,
        company_id: str,
        account_key: str,
        amo_author_id: object,
        amo_users_by_id: dict[str, dict[str, str]],
    ) -> str:
        if amo_author_id is None:
            raise ValueError("AmoCRM: для импорта сущности нужен created_by (id пользователя Amo)")
        key = str(amo_author_id).strip()
        if not key:
            raise ValueError("AmoCRM: пустой created_by")
        snap = amo_users_by_id.get(key)
        if snap is None:
            raise ValueError(
                f"AmoCRM: пользователь аккаунта id={key} отсутствует в ответе GET /api/v4/users"
            )
        email = snap.get("email", "").strip().lower()
        if not email:
            raise ValueError(
                f"AmoCRM: у пользователя id={key} нет email в каталоге аккаунта, импорт без автора невозможен"
            )
        display_name = snap.get("name") or None
        if display_name == "":
            display_name = None
        return await self._integration_author.resolve_platform_user_id(
            company_id=company_id,
            provider_id=AMO_PROVIDER_ID,
            account_key=account_key,
            external_user_id=key,
            email=email,
            display_name=display_name,
        )

    @staticmethod
    def _note_date_from_amo_created_at(created: object) -> date:
        """
        AmoCRM v4 отдаёт created_at как unix-seconds (число); в ответах бывает строка.
        Без распознанной даты ежедневник (фильтр по note_date) не покажет заметку.
        """
        if isinstance(created, (int, float)):
            return datetime.fromtimestamp(int(created), tz=UTC).date()
        if isinstance(created, str):
            s = created.strip()
            if not s:
                raise ValueError("AmoCRM note created_at is empty")
            if s.isdigit():
                return datetime.fromtimestamp(int(s), tz=UTC).date()
            normalized = s.replace("Z", "+00:00") if s.endswith("Z") else s
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError as exc:
                raise ValueError(f"AmoCRM note created_at is invalid: {created!r}") from exc
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC).date()
        raise ValueError(f"AmoCRM note created_at has unsupported type: {type(created).__name__}")

    async def _upsert_amocrm_note_if_text(
        self,
        *,
        raw: JsonObject,
        parent_entity: CRMEntity,
        namespace: str,
        company_id: str,
        account_key: str,
        auto_note_ai_analyze: bool,
        sync_user_id: str,
    ) -> bool:
        nid = raw.get("id")
        if nid is None:
            return False
        body = self._amo_note_plain_text(raw)
        if not body:
            return False
        label = self._mention_token_visible_name(parent_entity.name)
        token = f"[@{label}](entity:{parent_entity.entity_id})"
        description = f"{token}\n\n{body}"
        first_line = body.split("\n")[0].strip()
        name = first_line if first_line else f"Amo примечание {nid}"
        if len(name) > 500:
            name = name[:500]
        note_date = self._note_date_from_amo_created_at(raw.get("created_at"))
        patch_attrs: JsonObject = {}
        nt = raw.get("note_type")
        if nt is not None:
            patch_attrs["amo_note_type"] = nt
        cb = raw.get("created_by")
        if cb is not None:
            patch_attrs["amo_created_by"] = cb
        ent, created = await upsert_canonical_by_external_ref(
            entity_repo=self._entity_repo,
            namespace=namespace,
            company_id=company_id,
            user_id=sync_user_id,
            entity_type="note",
            source_id=AMO_PROVIDER_ID,
            record_id=str(nid),
            name=name,
            patch_attributes=patch_attrs,
            account_key=account_key,
            description=description,
            note_date=note_date,
        )
        await self._entity_service.apply_imported_note_graph_links(
            note_id=ent.entity_id,
            namespace=namespace,
            context_parent_entity_id=parent_entity.entity_id,
            user_id=sync_user_id,
        )
        if created and auto_note_ai_analyze:
            try:
                _ = await self._task_service.start_note_analyze(
                    note_id=ent.entity_id,
                    note_name=ent.name,
                    namespace=namespace,
                    mode="analyze",
                    config=NoteProcessingConfig(),
                )
            except ActiveTaskExistsError:
                pass
        return True

    async def _import_notes_for_amo_parent(
        self,
        *,
        base: str,
        access_token: str,
        api_segment: str,
        amo_element_id: str,
        parent_entity: CRMEntity,
        namespace: str,
        company_id: str,
        account_key: str,
        stats: dict[str, int],
        sync_user_id: str,
    ) -> None:
        auto_note_ai = await self._auto_note_ai_analyze_enabled(
            namespace=namespace,
            company_id=company_id,
        )
        url: str | None = f"{base}/api/v4/{api_segment}/{amo_element_id}/notes?limit=250"
        while url is not None:
            await asyncio.sleep(AMO_RPS_DELAY_SEC)
            payload = await self._get_json(url, access_token)
            for raw in self._embedded_list(payload, "notes"):
                imported = await self._upsert_amocrm_note_if_text(
                    raw=raw,
                    parent_entity=parent_entity,
                    namespace=namespace,
                    company_id=company_id,
                    account_key=account_key,
                    auto_note_ai_analyze=auto_note_ai,
                    sync_user_id=sync_user_id,
                )
                if imported:
                    stats["notes"] = stats.get("notes", 0) + 1
            url = self._next_page_url(payload)

    @staticmethod
    def _canonical_entity_type_for_amo_task_parent(amo_entity_type: object) -> str | None:
        if not isinstance(amo_entity_type, str):
            return None
        s = amo_entity_type.strip().lower()
        if s == "leads":
            return ENTITY_TYPE_BY_AMO_COLLECTION["leads"]
        if s == "contacts":
            return ENTITY_TYPE_BY_AMO_COLLECTION["contacts"]
        if s == "companies":
            return ENTITY_TYPE_BY_AMO_COLLECTION["companies"]
        return None

    @staticmethod
    def _amo_timestamp_to_date(ts: object) -> date | None:
        if not isinstance(ts, (int, float)):
            return None
        iv = int(ts)
        if iv <= 0:
            return None
        return datetime.fromtimestamp(iv, tz=UTC).date()

    async def _import_tasks(
        self,
        *,
        base: str,
        access_token: str,
        namespace: str,
        company_id: str,
        account_key: str,
        stats: dict[str, int],
        sync_user_id: str,
        on_batch: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        url: str | None = f"{base}/api/v4/tasks?limit=250"
        count = 0
        while url is not None:
            await asyncio.sleep(AMO_RPS_DELAY_SEC)
            payload = await self._get_json(url, access_token)
            for raw in self._embedded_list(payload, "tasks"):
                tid = raw.get("id")
                if tid is None:
                    raise ValueError("AmoCRM: в задаче нет id")
                amo_parent_type = raw.get("entity_type")
                amo_parent_id = raw.get("entity_id")
                if amo_parent_id is None:
                    stats["tasks_skipped_no_parent"] = stats.get("tasks_skipped_no_parent", 0) + 1
                    continue
                parent_type = self._canonical_entity_type_for_amo_task_parent(amo_parent_type)
                if parent_type is None:
                    stats["tasks_skipped_no_parent"] = stats.get("tasks_skipped_no_parent", 0) + 1
                    continue
                parent_eid = await self._resolve_canonical_entity_id(
                    company_id=company_id,
                    namespace=namespace,
                    entity_type=parent_type,
                    amo_record_id=str(amo_parent_id),
                )
                if parent_eid is None:
                    stats["tasks_skipped_no_parent"] = stats.get("tasks_skipped_no_parent", 0) + 1
                    continue

                body_lines: list[str] = []
                tx = raw.get("text")
                if isinstance(tx, str) and tx.strip():
                    body_lines.append(tx.strip())
                res = _as_json_object(raw.get("result"))
                if res is not None:
                    rt = res.get("text")
                    if isinstance(rt, str) and rt.strip():
                        body_lines.append(rt.strip())
                description = "\n\n".join(body_lines) if body_lines else None
                if description is None:
                    name = f"Задача Amo {tid}"
                else:
                    first_line = description.split("\n")[0].strip()
                    name = first_line if first_line else f"Задача Amo {tid}"
                if len(name) > 500:
                    name = name[:500]

                due = self._amo_timestamp_to_date(raw.get("complete_till"))

                attrs: JsonObject = {}
                amo_done = raw.get("is_completed") is True
                attrs["amo_is_completed"] = amo_done
                board_status = "done" if amo_done else "todo"
                tt_raw = raw.get("task_type_id")
                if tt_raw is not None:
                    if not isinstance(tt_raw, (str, int, float)) or isinstance(tt_raw, bool):
                        raise ValueError(f"AmoCRM: task_type_id не число для задачи {tid}")
                    try:
                        tt_int = int(tt_raw)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"AmoCRM: task_type_id не число для задачи {tid}") from exc
                    attrs["amo_task_type_id"] = tt_int
                    tname = AMO_STANDARD_TASK_TYPE_NAMES.get(tt_int)
                    if tname is not None:
                        attrs["amo_task_type_name"] = tname
                if res is not None:
                    rt_only = res.get("text")
                    if isinstance(rt_only, str) and rt_only.strip():
                        attrs["amo_result_text"] = rt_only.strip()

                tcb = raw.get("created_by")
                if tcb is not None:
                    attrs["amo_created_by"] = tcb

                task_ent, _ = await upsert_canonical_by_external_ref(
                    entity_repo=self._entity_repo,
                    namespace=namespace,
                    company_id=company_id,
                    user_id=sync_user_id,
                    entity_type="task",
                    source_id=AMO_PROVIDER_ID,
                    record_id=str(tid),
                    name=name,
                    patch_attributes=attrs,
                    account_key=account_key,
                    description=description,
                )
                task_eid = task_ent.entity_id
                await self._entity_service.sync_task_work_item(
                    task_ent,
                    CrmTaskWorkSeed(due_date=due, board_status=board_status),
                    user_id=sync_user_id,
                )

                created_rel = await self._ensure_relationship(
                    namespace=namespace,
                    company_id=company_id,
                    source_entity_id=task_eid,
                    target_entity_id=parent_eid,
                    relationship_type=RELATED_TO_RELATIONSHIP_TYPE,
                )
                if created_rel:
                    stats["relationships"] = stats.get("relationships", 0) + 1

                ru = raw.get("responsible_user_id")
                if ru is not None:
                    member_eid = await self._resolve_canonical_entity_id(
                        company_id=company_id,
                        namespace=namespace,
                        entity_type=AMO_USERS_ENTITY_TYPE_ID,
                        amo_record_id=str(ru),
                    )
                    if member_eid is not None:
                        created_as = await self._ensure_relationship(
                            namespace=namespace,
                            company_id=company_id,
                            source_entity_id=task_eid,
                            target_entity_id=member_eid,
                            relationship_type=ASSIGNED_TO_RELATIONSHIP_TYPE,
                        )
                        if created_as:
                            stats["relationships"] = stats.get("relationships", 0) + 1

                stats["tasks"] = stats.get("tasks", 0) + 1
                count += 1
                if on_batch is not None and count > 0 and count % AMO_PROGRESS_BATCH == 0:
                    await on_batch(count)
            url = self._next_page_url(payload)

    async def _import_collection(
        self,
        *,
        first_url: str,
        embedded_key: str,
        entity_type: str,
        namespace: str,
        company_id: str,
        user_id: str,
        access_token: str,
        account_key: str,
        map_item: AmoItemMapper,
        on_batch: Callable[[int], Awaitable[None]] | None = None,
    ) -> int:
        count = 0
        url: str | None = first_url
        while url is not None:
            await asyncio.sleep(AMO_RPS_DELAY_SEC)
            payload = await self._get_json(url, access_token)
            for raw in self._embedded_list(payload, embedded_key):
                await map_item(
                    raw,
                    namespace,
                    company_id,
                    user_id,
                    entity_type,
                    account_key,
                )
                count += 1
                if on_batch is not None and count > 0 and count % AMO_PROGRESS_BATCH == 0:
                    await on_batch(count)
            url = self._next_page_url(payload)
        return count

    def _phase_batch_hook(
        self,
        on_progress: AmoProgressFn,
        stage: str,
        lo: int,
        hi: int,
    ) -> Callable[[int], Awaitable[None]]:
        span = max(hi - lo - 1, 1)

        async def on_batch(count: int) -> None:
            step = min(span - 1, max(0, (count // AMO_PROGRESS_BATCH) * 3))
            await on_progress(stage, lo + min(step, span - 1))

        return on_batch

    async def sync_entities(
        self,
        namespace_name: str,
        *,
        on_progress: AmoProgressFn | None = None,
    ) -> dict[str, int]:
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("Контекст пользователя обязателен")
        company_id = ctx.active_company.company_id
        user_id = ctx.user.user_id

        try:
            access_token, sub = await self._get_token(
                company_id=company_id,
                user_id=user_id,
                namespace_name=namespace_name,
            )
        except OAuthTokenRefreshError as exc:
            raise ValueError("Сессия AmoCRM устарела, подключите интеграцию снова") from exc

        base = self._api_base(sub)
        stats: dict[str, int] = {
            "relationships": 0,
            "notes": 0,
            "tasks": 0,
            "tasks_skipped_no_parent": 0,
        }

        await asyncio.sleep(AMO_RPS_DELAY_SEC)
        users_payload_prefetch = await self._get_json(
            f"{base}/api/v4/{AMO_USERS_PATH}", access_token
        )
        embedded_prefetch = _as_json_object(users_payload_prefetch.get("_embedded"))
        users_raw_cached = embedded_prefetch.get("users") if embedded_prefetch is not None else None
        users_list_cached = (
            cast(list[object], users_raw_cached) if isinstance(users_raw_cached, list) else []
        )
        _ = self._amo_users_directory_from_api(users_list_cached)

        if on_progress is not None:
            await on_progress("contacts", 0)

        async def map_lead(
            raw: JsonObject,
            ns: str,
            cid: str,
            uid: str,
            et: str,
            account_key: str,
        ) -> None:
            rid = raw.get("id")
            if rid is None:
                raise ValueError("AmoCRM: в элементе нет id")
            nm = raw.get("name")
            name = str(nm) if isinstance(nm, str) and nm.strip() else f"lead {rid}"
            price = raw.get("price")
            st = raw.get("status_id")
            pl = raw.get("pipeline_id")
            attrs: JsonObject = {}
            if isinstance(price, (int, float)):
                attrs["price"] = price
            if st is not None:
                attrs["status_id"] = st
            if pl is not None:
                attrs["pipeline_id"] = pl
            lcb = raw.get("created_by")
            if lcb is not None:
                attrs["amo_created_by"] = lcb
            lead_ent, _ = await upsert_canonical_by_external_ref(
                entity_repo=self._entity_repo,
                namespace=ns,
                company_id=cid,
                user_id=uid,
                entity_type=et,
                source_id=AMO_PROVIDER_ID,
                record_id=str(rid),
                name=name,
                patch_attributes=attrs,
                account_key=account_key,
            )
            lead_eid = lead_ent.entity_id
            for amo_contact_id in self._amo_ids_from_item_embedded(raw, "contacts"):
                tgt = await self._resolve_canonical_entity_id(
                    company_id=cid,
                    namespace=ns,
                    entity_type=ENTITY_TYPE_BY_AMO_COLLECTION["contacts"],
                    amo_record_id=amo_contact_id,
                )
                if tgt is None:
                    continue
                created = await self._ensure_relationship(
                    namespace=ns,
                    company_id=cid,
                    source_entity_id=lead_eid,
                    target_entity_id=tgt,
                    relationship_type=RELATED_TO_RELATIONSHIP_TYPE,
                )
                if created:
                    stats["relationships"] += 1
            for amo_org_id in self._amo_ids_from_item_embedded(raw, "companies"):
                tgt = await self._resolve_canonical_entity_id(
                    company_id=cid,
                    namespace=ns,
                    entity_type=ENTITY_TYPE_BY_AMO_COLLECTION["companies"],
                    amo_record_id=amo_org_id,
                )
                if tgt is None:
                    continue
                created = await self._ensure_relationship(
                    namespace=ns,
                    company_id=cid,
                    source_entity_id=lead_eid,
                    target_entity_id=tgt,
                    relationship_type=RELATED_TO_RELATIONSHIP_TYPE,
                )
                if created:
                    stats["relationships"] += 1
            await self._import_notes_for_amo_parent(
                base=base,
                access_token=access_token,
                api_segment="leads",
                amo_element_id=str(rid),
                parent_entity=lead_ent,
                namespace=ns,
                company_id=cid,
                account_key=account_key,
                stats=stats,
                sync_user_id=uid,
            )

        async def map_contact(
            raw: JsonObject,
            ns: str,
            cid: str,
            uid: str,
            et: str,
            account_key: str,
        ) -> None:
            rid = raw.get("id")
            if rid is None:
                raise ValueError("AmoCRM: в элементе нет id")
            parts = [raw.get("first_name"), raw.get("last_name")]
            nmp = " ".join(str(p) for p in parts if isinstance(p, str) and p.strip())
            name = nmp if nmp.strip() else f"contact {rid}"
            attrs: JsonObject = {}
            if isinstance(raw.get("first_name"), str):
                attrs["first_name"] = raw.get("first_name")
            if isinstance(raw.get("last_name"), str):
                attrs["last_name"] = raw.get("last_name")
            ccb = raw.get("created_by")
            if ccb is not None:
                attrs["amo_created_by"] = ccb
            contact_ent, _ = await upsert_canonical_by_external_ref(
                entity_repo=self._entity_repo,
                namespace=ns,
                company_id=cid,
                user_id=uid,
                entity_type=et,
                source_id=AMO_PROVIDER_ID,
                record_id=str(rid),
                name=name,
                patch_attributes=attrs,
                account_key=account_key,
            )
            contact_eid = contact_ent.entity_id
            org_type = ENTITY_TYPE_BY_AMO_COLLECTION["companies"]
            for amo_org_id in self._amo_ids_from_item_embedded(raw, "companies"):
                tgt = await self._resolve_canonical_entity_id(
                    company_id=cid,
                    namespace=ns,
                    entity_type=org_type,
                    amo_record_id=amo_org_id,
                )
                if tgt is None:
                    continue
                created = await self._ensure_relationship(
                    namespace=ns,
                    company_id=cid,
                    source_entity_id=contact_eid,
                    target_entity_id=tgt,
                    relationship_type=BELONGS_TO_RELATIONSHIP_TYPE,
                )
                if created:
                    stats["relationships"] += 1
            await self._import_notes_for_amo_parent(
                base=base,
                access_token=access_token,
                api_segment="contacts",
                amo_element_id=str(rid),
                parent_entity=contact_ent,
                namespace=ns,
                company_id=cid,
                account_key=account_key,
                stats=stats,
                sync_user_id=uid,
            )

        async def map_company(
            raw: JsonObject,
            ns: str,
            cid: str,
            uid: str,
            et: str,
            account_key: str,
        ) -> None:
            rid = raw.get("id")
            if rid is None:
                raise ValueError("AmoCRM: в элементе нет id")
            nm = raw.get("name")
            name = str(nm) if isinstance(nm, str) and nm.strip() else f"organization {rid}"
            org_attrs: JsonObject = {}
            ocb = raw.get("created_by")
            if ocb is not None:
                org_attrs["amo_created_by"] = ocb
            org_ent, _ = await upsert_canonical_by_external_ref(
                entity_repo=self._entity_repo,
                namespace=ns,
                company_id=cid,
                user_id=uid,
                entity_type=et,
                source_id=AMO_PROVIDER_ID,
                record_id=str(rid),
                name=name,
                patch_attributes=org_attrs,
                account_key=account_key,
            )
            await self._import_notes_for_amo_parent(
                base=base,
                access_token=access_token,
                api_segment="companies",
                amo_element_id=str(rid),
                parent_entity=org_ent,
                namespace=ns,
                company_id=cid,
                account_key=account_key,
                stats=stats,
                sync_user_id=uid,
            )

        contacts_batch = (
            self._phase_batch_hook(on_progress, "contacts", 0, 25)
            if on_progress is not None
            else None
        )
        n_ct = await self._import_collection(
            first_url=f"{base}/api/v4/contacts?limit=250&with=companies",
            embedded_key="contacts",
            entity_type=ENTITY_TYPE_BY_AMO_COLLECTION["contacts"],
            namespace=namespace_name,
            company_id=company_id,
            user_id=user_id,
            access_token=access_token,
            account_key=sub,
            map_item=map_contact,
            on_batch=contacts_batch,
        )
        stats["contacts"] = n_ct
        if on_progress is not None:
            await on_progress("contacts", 25)

        if on_progress is not None:
            await on_progress("companies", 25)
        companies_batch = (
            self._phase_batch_hook(on_progress, "companies", 25, 50)
            if on_progress is not None
            else None
        )
        n_co = await self._import_collection(
            first_url=f"{base}/api/v4/companies?limit=250",
            embedded_key="companies",
            entity_type=ENTITY_TYPE_BY_AMO_COLLECTION["companies"],
            namespace=namespace_name,
            company_id=company_id,
            user_id=user_id,
            access_token=access_token,
            account_key=sub,
            map_item=map_company,
            on_batch=companies_batch,
        )
        stats["companies"] = n_co
        if on_progress is not None:
            await on_progress("companies", 50)

        if on_progress is not None:
            await on_progress("leads", 50)
        leads_batch = (
            self._phase_batch_hook(on_progress, "leads", 50, 75)
            if on_progress is not None
            else None
        )
        n_leads = await self._import_collection(
            first_url=f"{base}/api/v4/leads?limit=250&with=contacts%2Ccompanies",
            embedded_key="leads",
            entity_type=ENTITY_TYPE_BY_AMO_COLLECTION["leads"],
            namespace=namespace_name,
            company_id=company_id,
            user_id=user_id,
            access_token=access_token,
            account_key=sub,
            map_item=map_lead,
            on_batch=leads_batch,
        )
        stats["leads"] = n_leads
        if on_progress is not None:
            await on_progress("leads", 75)

        if on_progress is not None:
            await on_progress("users", 75)
        u_count = 0
        for raw_item in users_list_cached:
            raw = _as_json_object(raw_item)
            if raw is None:
                continue
            tid = raw.get("id")
            if tid is None:
                continue
            name = str(raw.get("name") or raw.get("title") or f"member {tid}")
            attrs: JsonObject = {}
            if raw.get("email") is not None:
                attrs["email"] = str(raw.get("email"))
            if raw.get("is_active") is not None:
                attrs["is_active"] = bool(raw.get("is_active"))
            _, _ = await upsert_canonical_by_external_ref(
                entity_repo=self._entity_repo,
                namespace=namespace_name,
                company_id=company_id,
                user_id=user_id,
                entity_type=AMO_USERS_ENTITY_TYPE_ID,
                source_id=AMO_PROVIDER_ID,
                record_id=str(tid),
                name=name,
                patch_attributes=attrs,
                account_key=sub,
            )
            u_count += 1
        stats["users"] = u_count
        if on_progress is not None:
            await on_progress("users", 82)

        if on_progress is not None:
            await on_progress("tasks", 82)
        tasks_batch = (
            self._phase_batch_hook(on_progress, "tasks", 82, 100)
            if on_progress is not None
            else None
        )
        await self._import_tasks(
            base=base,
            access_token=access_token,
            namespace=namespace_name,
            company_id=company_id,
            account_key=sub,
            stats=stats,
            sync_user_id=user_id,
            on_batch=tasks_batch,
        )
        if on_progress is not None:
            await on_progress("tasks", 100)

        return stats

    async def sync_custom_field_catalog(
        self,
        namespace_name: str,
        *,
        on_progress: AmoProgressFn | None = None,
    ) -> dict[str, int]:
        """
        Подмешивает в optional_fields канонических типов сущностей (lead, contact, organization) поля amo_cf_<field_id> по справочнику custom_fields.
        """
        ctx = get_context()
        if ctx is None or ctx.active_company is None:
            raise ValueError("Контекст пользователя обязателен")
        company_id = ctx.active_company.company_id
        user_id = ctx.user.user_id

        try:
            access_token, sub = await self._get_token(
                company_id=company_id,
                user_id=user_id,
                namespace_name=namespace_name,
            )
        except OAuthTokenRefreshError as exc:
            raise ValueError("Сессия AmoCRM устарела, подключите интеграцию снова") from exc

        base = self._api_base(sub)
        updated: dict[str, int] = {}
        segments = list(ENTITY_TYPE_BY_AMO_COLLECTION.items())
        n_seg = len(segments)

        for seg_i, (segment, type_id) in enumerate(segments):
            if on_progress is not None and n_seg > 0:
                await on_progress(
                    "custom_fields",
                    min(99, int(100 * seg_i / n_seg)),
                )
            await asyncio.sleep(AMO_RPS_DELAY_SEC)
            data = await self._get_json(
                f"{base}/api/v4/{segment}/custom_fields",
                access_token,
            )
            embedded = _as_json_object(data.get("_embedded"))
            fields_raw = embedded.get("custom_fields") if embedded is not None else None
            fields = cast(list[object], fields_raw) if isinstance(fields_raw, list) else []
            et = await self._entity_type_repo.get_by_type_id(
                type_id,
                namespace=namespace_name,
                company_id=company_id,
            )
            if et is None:
                updated[type_id] = 0
                continue
            opt: JsonObject = dict(et.optional_fields) if et.optional_fields else {}
            n_add = 0
            for raw_field in fields:
                field = _as_json_object(raw_field)
                if field is None:
                    continue
                fid = field.get("id")
                if fid is None:
                    continue
                key = f"amo_cf_{fid}"
                if key in opt:
                    continue
                nm = field.get("name")
                label = str(nm) if isinstance(nm, str) else f"amo field {fid}"
                ftype = field.get("type")
                schema_type = "string"
                if ftype in ("numeric", "monetary"):
                    schema_type = "number"
                if ftype in ("select", "multiselect", "radiobutton", "category"):
                    schema_type = "string"
                opt[key] = {
                    "type": schema_type,
                    "label": label,
                    "description": f"AmoCRM custom field id={fid}",
                }
                n_add += 1
            if n_add:
                _ = await self._entity_type_repo.update_metadata(
                    type_id,
                    namespace=namespace_name,
                    company_id=company_id,
                    optional_fields=opt,
                )
            updated[type_id] = n_add

        if on_progress is not None:
            await on_progress("custom_fields", 100)

        return updated
