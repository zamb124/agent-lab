"""
Интеграция AmoCRM: OAuth service key, импорт сущностей v4, справочник custom_fields.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone
from typing import Any, Optional

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
from apps.crm.services.entity_service import EntityService
from apps.crm.services.task_service import ActiveTaskExistsError, TaskService
from core.context import get_context
from core.identity.integration_external_author import IntegrationExternalAuthorService
from core.db.repositories.namespace_repository import NamespaceRepository
from core.http.client import get_httpx_client
from core.integrations.models import IntegrationProvider
from core.integrations.oauth_service import OAuthService, OAuthTokenRefreshError

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
        self._oauth = oauth_service
        self._entity_repo = entity_repository
        self._entity_type_repo = entity_type_repository
        self._relationship_repo = relationship_repository
        self._entity_service = entity_service
        self._namespace_repo = namespace_repository
        self._task_service = task_service
        self._integration_author = integration_external_author

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
        if not isinstance(access, str) or not access:
            raise ValueError("Пустой access_token AmoCRM")
        return access, sub_raw.strip()

    async def _get_json(
        self,
        url: str,
        access_token: str,
    ) -> dict[str, Any]:
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
        response.raise_for_status()
        if response.status_code == 204:
            return {}
        if not response.content.strip():
            return {}
        return response.json()

    def _next_page_url(self, payload: dict[str, Any]) -> str | None:
        links = payload.get("_links")
        if not isinstance(links, dict):
            return None
        nxt = links.get("next")
        if isinstance(nxt, dict):
            href = nxt.get("href")
            if isinstance(href, str) and href.strip():
                return href.strip()
        return None

    def _embedded_list(self, payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
        emb = payload.get("_embedded")
        if not isinstance(emb, dict):
            return []
        raw = emb.get(key)
        if not isinstance(raw, list):
            return []
        return [x for x in raw if isinstance(x, dict)]

    @staticmethod
    def _amo_ids_from_embedded_dict(emb: Any, key: str) -> list[str]:
        if not isinstance(emb, dict):
            return []
        items = emb.get(key)
        if not isinstance(items, list):
            return []
        out: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            iid = item.get("id")
            if iid is None:
                continue
            s = str(iid).strip()
            if s:
                out.append(s)
        return out

    @staticmethod
    def _amo_ids_from_item_embedded(raw: dict[str, Any], key: str) -> list[str]:
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
            attributes={},
        )
        await self._relationship_repo.create(rel)
        return True

    @staticmethod
    def _amo_note_plain_text(raw: dict[str, Any]) -> str | None:
        t = raw.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
        params = raw.get("params")
        if isinstance(params, dict):
            pt = params.get("text")
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
    def _amo_users_directory_from_api(users: list[Any]) -> dict[str, dict[str, str]]:
        out: dict[str, dict[str, str]] = {}
        for raw in users:
            if not isinstance(raw, dict):
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
        amo_author_id: Any,
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
    def _note_date_from_amo_created_at(created: Any, *, fallback: date) -> date:
        """
        AmoCRM v4 отдаёт created_at как unix-seconds (число); в ответах бывает строка.
        Без распознанной даты ежедневник (фильтр по note_date) не покажет заметку.
        """
        if isinstance(created, (int, float)):
            return datetime.fromtimestamp(int(created), tz=timezone.utc).date()
        if isinstance(created, str):
            s = created.strip()
            if not s:
                return fallback
            if s.isdigit():
                return datetime.fromtimestamp(int(s), tz=timezone.utc).date()
            normalized = s.replace("Z", "+00:00") if s.endswith("Z") else s
            try:
                dt = datetime.fromisoformat(normalized)
            except ValueError:
                return fallback
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).date()
        return fallback

    async def _upsert_amocrm_note_if_text(
        self,
        *,
        raw: dict[str, Any],
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
        parent_ts = parent_entity.created_at
        if parent_ts is None:
            raise ValueError("parent_entity.created_at обязателен для импорта примечания AmoCRM")
        fallback_date = parent_ts.astimezone(timezone.utc).date()
        note_date = self._note_date_from_amo_created_at(
            raw.get("created_at"),
            fallback=fallback_date,
        )
        patch_attrs: dict[str, Any] = {}
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
                await self._task_service.start_note_analyze(
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
    def _canonical_entity_type_for_amo_task_parent(amo_entity_type: Any) -> str | None:
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
    def _amo_timestamp_to_date(ts: Any) -> date | None:
        if not isinstance(ts, (int, float)):
            return None
        iv = int(ts)
        if iv <= 0:
            return None
        return datetime.fromtimestamp(iv, tz=timezone.utc).date()

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
        on_batch: Optional[Callable[[int], Awaitable[None]]] = None,
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
                res = raw.get("result")
                if isinstance(res, dict):
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

                attrs: dict[str, Any] = {}
                amo_done = raw.get("is_completed") is True
                attrs["amo_is_completed"] = amo_done
                attrs["status"] = "done" if amo_done else "todo"
                tt_raw = raw.get("task_type_id")
                if tt_raw is not None:
                    try:
                        tt_int = int(tt_raw)
                    except (TypeError, ValueError) as exc:
                        raise ValueError(f"AmoCRM: task_type_id не число для задачи {tid}") from exc
                    attrs["amo_task_type_id"] = tt_int
                    tname = AMO_STANDARD_TASK_TYPE_NAMES.get(tt_int)
                    if tname is not None:
                        attrs["amo_task_type_name"] = tname
                if isinstance(res, dict):
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
                    due_date=due,
                )
                task_eid = task_ent.entity_id

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
                if (
                    on_batch is not None
                    and count > 0
                    and count % AMO_PROGRESS_BATCH == 0
                ):
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
        map_item: Any,
        on_batch: Optional[Callable[[int], Awaitable[None]]] = None,
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
                if (
                    on_batch is not None
                    and count > 0
                    and count % AMO_PROGRESS_BATCH == 0
                ):
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
        on_progress: Optional[AmoProgressFn] = None,
    ) -> dict[str, int]:
        ctx = get_context()
        if ctx is None or ctx.user is None or ctx.active_company is None:
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
        users_list_cached = (users_payload_prefetch.get("_embedded") or {}).get("users")
        if not isinstance(users_list_cached, list):
            users_list_cached = []
        amo_users_by_id = self._amo_users_directory_from_api(users_list_cached)

        if on_progress is not None:
            await on_progress("contacts", 0)

        async def map_lead(
            raw: dict[str, Any],
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
            attrs: dict[str, Any] = {}
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
            raw: dict[str, Any],
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
            attrs: dict[str, Any] = {}
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
            raw: dict[str, Any],
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
            org_attrs: dict[str, Any] = {}
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
        for raw in users_list_cached:
            if not isinstance(raw, dict):
                continue
            tid = raw.get("id")
            if tid is None:
                continue
            name = str(raw.get("name") or raw.get("title") or f"member {tid}")
            attrs: dict[str, Any] = {}
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
        on_progress: Optional[AmoProgressFn] = None,
    ) -> dict[str, int]:
        """
        Подмешивает в optional_fields канонических типов сущностей (lead, contact, organization) поля amo_cf_<field_id> по справочнику custom_fields.
        """
        ctx = get_context()
        if ctx is None or ctx.user is None or ctx.active_company is None:
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
            fields = (data.get("_embedded") or {}).get("custom_fields")
            if not isinstance(fields, list):
                fields = []
            et = await self._entity_type_repo.get_by_type_id(type_id, company_id=company_id)
            if et is None:
                updated[type_id] = 0
                continue
            opt = dict(et.optional_fields) if et.optional_fields else {}
            n_add = 0
            for field in fields:
                if not isinstance(field, dict):
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
                await self._entity_type_repo.update_metadata(
                    type_id, company_id=company_id, optional_fields=opt
                )
            updated[type_id] = n_add

        if on_progress is not None:
            await on_progress("custom_fields", 100)

        return updated
