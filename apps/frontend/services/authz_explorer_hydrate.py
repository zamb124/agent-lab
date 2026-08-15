"""Гидрация title/href для Access Explorer из доменных репозиториев и PK-select."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from apps.crm.db.base import CRMDatabase
from apps.crm.db.models import CRMEntity
from apps.flows.src.db.flow_repository import FlowRepository
from apps.office.db.base import OfficeDatabase
from apps.office.db.models import OfficeDocumentBinding, OfficeDocumentCatalog
from apps.sync.db.base import SyncDatabase
from apps.sync.db.models import SyncChannel
from apps.wiki.db.base import WikiDatabase
from apps.wiki.db.models import WikiPageRow
from core.authz.explorer import AuthzExplorerObjectHit, AuthzTitleStatus
from core.authz.ids import format_namespace_key, parse_flow_branch_key, parse_namespace_key
from core.authz.types import AuthzObjectType
from core.config import get_settings
from core.mail.models import MailboxBinding
from core.mail.repositories import MailboxBindingRepository
from core.worktracker.db import WorktrackerDatabase
from core.worktracker.db_models import WorkQueueRow

_SEARCH_LIMIT = 40


@dataclass(frozen=True, slots=True)
class AuthzHydratedObject:
    object_type: AuthzObjectType
    object_key: str
    title: str | None
    title_status: AuthzTitleStatus
    href: str
    manage_href: str
    namespace: str | None
    company_id: str | None


def explorer_hrefs(
    object_type: AuthzObjectType, object_key: str, *, namespace: str | None
) -> tuple[str, str]:
    if object_type is AuthzObjectType.WIKI_PAGE:
        href = f"/wiki/p/{object_key}"
        return href, f"{href}?access=1"
    if object_type is AuthzObjectType.CRM_ENTITY:
        href = f"/crm/entities/{object_key}"
        return href, f"{href}?access=1"
    if object_type is AuthzObjectType.CRM_NAMESPACE:
        _company_id, ns = parse_namespace_key(object_key)
        href = f"/crm/namespaces/{ns}"
        return href, ""
    if object_type is AuthzObjectType.OFFICE_DOCUMENT:
        href = f"/documents/edit/{object_key}"
        return href, f"{href}?access=1"
    if object_type is AuthzObjectType.OFFICE_CATALOG:
        return "/documents", f"/documents?catalog_id={object_key}&access=1"
    if object_type is AuthzObjectType.FLOW:
        _company_id, flow_id = parse_namespace_key(object_key)
        href = f"/flows/{flow_id}"
        return href, ""
    if object_type is AuthzObjectType.FLOW_BRANCH:
        _company_id, flow_id, _branch_id = parse_flow_branch_key(object_key)
        href = f"/flows/{flow_id}"
        return href, ""
    if object_type is AuthzObjectType.TOOL:
        return "/flows", ""
    if object_type is AuthzObjectType.FLOW_UI_SHARE:
        return "/flows", ""
    if object_type is AuthzObjectType.SYNC_CHANNEL:
        href = f"/sync/c/{object_key}"
        return href, ""
    if object_type is AuthzObjectType.WORK_QUEUE:
        return "/worktracker", ""
    if object_type is AuthzObjectType.MAILBOX_BINDING:
        return "/settings", ""
    if object_type is AuthzObjectType.PLATFORM_NAMESPACE:
        return "/namespaces", ""
    if object_type is AuthzObjectType.AGENT_DEVICE:
        return "/settings", ""
    _ = namespace
    return "", ""


class AuthzExplorerHydrator:
    def __init__(
        self,
        *,
        flow_repository: FlowRepository,
        mailbox_binding_repository: MailboxBindingRepository,
    ) -> None:
        self._flow_repository: FlowRepository = flow_repository
        self._mailbox_binding_repository: MailboxBindingRepository = (
            mailbox_binding_repository
        )
        self._wiki_db: WikiDatabase | None = None
        self._crm_db: CRMDatabase | None = None
        self._office_db: OfficeDatabase | None = None
        self._sync_db: SyncDatabase | None = None
        self._worktracker_db: WorktrackerDatabase | None = None
        self._wiki_unavailable: bool = False
        self._crm_unavailable: bool = False
        self._office_unavailable: bool = False
        self._sync_unavailable: bool = False
        self._worktracker_unavailable: bool = False

    def _wiki(self) -> WikiDatabase | None:
        if self._wiki_unavailable:
            return None
        if self._wiki_db is not None:
            return self._wiki_db
        url = get_settings().database.wiki_url
        if url is None or url.strip() == "":
            self._wiki_unavailable = True
            return None
        self._wiki_db = WikiDatabase(url)
        return self._wiki_db

    def _crm(self) -> CRMDatabase | None:
        if self._crm_unavailable:
            return None
        if self._crm_db is not None:
            return self._crm_db
        url = get_settings().database.crm_url
        if url is None or url.strip() == "":
            self._crm_unavailable = True
            return None
        self._crm_db = CRMDatabase.get_instance(url)
        return self._crm_db

    def _office(self) -> OfficeDatabase | None:
        if self._office_unavailable:
            return None
        if self._office_db is not None:
            return self._office_db
        url = get_settings().database.office_url
        if url is None or url.strip() == "":
            self._office_unavailable = True
            return None
        self._office_db = OfficeDatabase.get_instance(url)
        return self._office_db

    def _sync(self) -> SyncDatabase | None:
        if self._sync_unavailable:
            return None
        if self._sync_db is not None:
            return self._sync_db
        url = get_settings().database.sync_url
        if url is None or url.strip() == "":
            self._sync_unavailable = True
            return None
        self._sync_db = SyncDatabase.get_instance(url)
        return self._sync_db

    def _worktracker(self) -> WorktrackerDatabase | None:
        if self._worktracker_unavailable:
            return None
        if self._worktracker_db is not None:
            return self._worktracker_db
        url = get_settings().database.worktracker_url
        if url is None or url.strip() == "":
            self._worktracker_unavailable = True
            return None
        self._worktracker_db = WorktrackerDatabase(url)
        return self._worktracker_db

    async def hydrate(
        self,
        object_type: AuthzObjectType,
        object_key: str,
        *,
        company_id: str,
    ) -> AuthzHydratedObject:
        if object_type is AuthzObjectType.PLATFORM_NAMESPACE:
            return self._hydrate_namespace(object_type, object_key, company_id)
        if object_type is AuthzObjectType.CRM_NAMESPACE:
            return self._hydrate_namespace(object_type, object_key, company_id)
        if object_type is AuthzObjectType.WIKI_PAGE:
            return await self._hydrate_wiki_page(object_key, company_id)
        if object_type is AuthzObjectType.CRM_ENTITY:
            return await self._hydrate_crm_entity(object_key, company_id)
        if object_type is AuthzObjectType.OFFICE_CATALOG:
            return await self._hydrate_office_catalog(object_key, company_id)
        if object_type is AuthzObjectType.OFFICE_DOCUMENT:
            return await self._hydrate_office_document(object_key, company_id)
        if object_type is AuthzObjectType.FLOW:
            return await self._hydrate_flow(object_key, company_id)
        if object_type is AuthzObjectType.FLOW_BRANCH:
            return self._hydrate_flow_branch(object_key, company_id)
        if object_type is AuthzObjectType.TOOL:
            return self._hydrate_tool(object_key, company_id)
        if object_type is AuthzObjectType.SYNC_CHANNEL:
            return await self._hydrate_sync_channel(object_key, company_id)
        if object_type is AuthzObjectType.WORK_QUEUE:
            return await self._hydrate_work_queue(object_key, company_id)
        if object_type is AuthzObjectType.MAILBOX_BINDING:
            return await self._hydrate_mailbox(object_key, company_id)
        href, manage_href = explorer_hrefs(object_type, object_key, namespace=None)
        return AuthzHydratedObject(
            object_type=object_type,
            object_key=object_key,
            title=None,
            title_status=AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=None,
        )

    def _hydrate_namespace(
        self,
        object_type: AuthzObjectType,
        object_key: str,
        company_id: str,
    ) -> AuthzHydratedObject:
        key_company_id, namespace = parse_namespace_key(object_key)
        href, manage_href = explorer_hrefs(object_type, object_key, namespace=namespace)
        if key_company_id != company_id:
            return AuthzHydratedObject(
                object_type=object_type,
                object_key=object_key,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=namespace,
                company_id=key_company_id,
            )
        return AuthzHydratedObject(
            object_type=object_type,
            object_key=object_key,
            title=namespace,
            title_status=AuthzTitleStatus.LOADED,
            href=href,
            manage_href=manage_href,
            namespace=namespace,
            company_id=key_company_id,
        )

    async def _hydrate_wiki_page(
        self, wiki_page_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.WIKI_PAGE, wiki_page_id, namespace=None
        )
        db = self._wiki()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.WIKI_PAGE,
                object_key=wiki_page_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(WikiPageRow).where(
                        WikiPageRow.wiki_page_id == wiki_page_id,
                        WikiPageRow.company_id == company_id,
                        WikiPageRow.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.WIKI_PAGE,
                object_key=wiki_page_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        title = row.title.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.WIKI_PAGE,
            object_key=wiki_page_id,
            title=title if title != "" else None,
            title_status=AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=row.namespace,
            company_id=row.company_id,
        )

    async def _hydrate_crm_entity(
        self, entity_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.CRM_ENTITY, entity_id, namespace=None
        )
        db = self._crm()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.CRM_ENTITY,
                object_key=entity_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(CRMEntity).where(
                        CRMEntity.entity_id == entity_id,
                        CRMEntity.company_id == company_id,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.CRM_ENTITY,
                object_key=entity_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        name = row.name.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.CRM_ENTITY,
            object_key=entity_id,
            title=name if name != "" else None,
            title_status=AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=row.namespace,
            company_id=row.company_id,
        )

    async def _hydrate_office_catalog(
        self, catalog_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.OFFICE_CATALOG, catalog_id, namespace=None
        )
        db = self._office()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.OFFICE_CATALOG,
                object_key=catalog_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(OfficeDocumentCatalog).where(
                        OfficeDocumentCatalog.catalog_id == catalog_id,
                        OfficeDocumentCatalog.company_id == company_id,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.OFFICE_CATALOG,
                object_key=catalog_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        title = row.title.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.OFFICE_CATALOG,
            object_key=catalog_id,
            title=title if title != "" else None,
            title_status=AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=row.namespace,
            company_id=row.company_id,
        )

    async def _hydrate_office_document(
        self, file_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.OFFICE_DOCUMENT, file_id, namespace=None
        )
        db = self._office()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.OFFICE_DOCUMENT,
                object_key=file_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(OfficeDocumentBinding).where(
                        OfficeDocumentBinding.file_id == file_id,
                        OfficeDocumentBinding.company_id == company_id,
                        OfficeDocumentBinding.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.OFFICE_DOCUMENT,
                object_key=file_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        title = row.title.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.OFFICE_DOCUMENT,
            object_key=file_id,
            title=title if title != "" else None,
            title_status=AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=row.namespace,
            company_id=row.company_id,
        )

    async def _hydrate_flow(self, object_key: str, company_id: str) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(AuthzObjectType.FLOW, object_key, namespace=None)
        key_company_id, flow_id = parse_namespace_key(object_key)
        if key_company_id != company_id:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.FLOW,
                object_key=object_key,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        config = await self._flow_repository.get_latest(flow_id)
        if config is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.FLOW,
                object_key=object_key,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        name = config.name.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.FLOW,
            object_key=object_key,
            title=name if name != "" else None,
            title_status=AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=company_id,
        )

    def _hydrate_flow_branch(
        self, object_key: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.FLOW_BRANCH, object_key, namespace=None
        )
        key_company_id, _flow_id, _branch_id = parse_flow_branch_key(object_key)
        matched = key_company_id == company_id
        return AuthzHydratedObject(
            object_type=AuthzObjectType.FLOW_BRANCH,
            object_key=object_key,
            title=None,
            title_status=AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=company_id if matched else None,
        )

    def _hydrate_tool(self, object_key: str, company_id: str) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.TOOL, object_key, namespace=None
        )
        key_company_id, _tool_id = parse_namespace_key(object_key)
        matched = key_company_id == company_id
        return AuthzHydratedObject(
            object_type=AuthzObjectType.TOOL,
            object_key=object_key,
            title=None,
            title_status=AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=company_id if matched else None,
        )

    async def _hydrate_sync_channel(
        self, channel_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.SYNC_CHANNEL, channel_id, namespace=None
        )
        db = self._sync()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.SYNC_CHANNEL,
                object_key=channel_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(SyncChannel).where(
                        SyncChannel.channel_id == channel_id,
                        SyncChannel.company_id == company_id,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.SYNC_CHANNEL,
                object_key=channel_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        raw_name = row.name
        title = raw_name.strip() if raw_name is not None else ""
        return AuthzHydratedObject(
            object_type=AuthzObjectType.SYNC_CHANNEL,
            object_key=channel_id,
            title=title if title != "" else None,
            title_status=AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=row.namespace,
            company_id=row.company_id,
        )

    async def _hydrate_work_queue(
        self, work_queue_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.WORK_QUEUE, work_queue_id, namespace=None
        )
        db = self._worktracker()
        if db is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.WORK_QUEUE,
                object_key=work_queue_id,
                title=None,
                title_status=AuthzTitleStatus.UNAVAILABLE,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        async with db.session() as session:
            row = (
                await session.execute(
                    select(WorkQueueRow).where(
                        WorkQueueRow.work_queue_id == work_queue_id,
                        WorkQueueRow.company_id == company_id,
                    )
                )
            ).scalar_one_or_none()
        if row is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.WORK_QUEUE,
                object_key=work_queue_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        name = row.name.strip()
        return AuthzHydratedObject(
            object_type=AuthzObjectType.WORK_QUEUE,
            object_key=work_queue_id,
            title=name if name != "" else None,
            title_status=AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=row.company_id,
        )

    async def _hydrate_mailbox(
        self, mailbox_binding_id: str, company_id: str
    ) -> AuthzHydratedObject:
        href, manage_href = explorer_hrefs(
            AuthzObjectType.MAILBOX_BINDING, mailbox_binding_id, namespace=None
        )
        binding: MailboxBinding | None = await self._mailbox_binding_repository.get(
            mailbox_binding_id, company_id
        )
        if binding is None:
            return AuthzHydratedObject(
                object_type=AuthzObjectType.MAILBOX_BINDING,
                object_key=mailbox_binding_id,
                title=None,
                title_status=AuthzTitleStatus.MISSING,
                href=href,
                manage_href=manage_href,
                namespace=None,
                company_id=None,
            )
        return AuthzHydratedObject(
            object_type=AuthzObjectType.MAILBOX_BINDING,
            object_key=mailbox_binding_id,
            title=binding.email_address,
            title_status=AuthzTitleStatus.LOADED,
            href=href,
            manage_href=manage_href,
            namespace=None,
            company_id=binding.company_id,
        )

    async def search_objects(
        self,
        *,
        company_id: str,
        query: str,
        object_type: AuthzObjectType | None,
    ) -> list[AuthzExplorerObjectHit]:
        types: tuple[AuthzObjectType, ...]
        if object_type is not None:
            types = (object_type,)
        else:
            types = (
                AuthzObjectType.WIKI_PAGE,
                AuthzObjectType.CRM_ENTITY,
                AuthzObjectType.OFFICE_DOCUMENT,
                AuthzObjectType.FLOW,
                AuthzObjectType.SYNC_CHANNEL,
            )
        hits: list[AuthzExplorerObjectHit] = []
        for search_type in types:
            hits.extend(
                await self._search_type(search_type, company_id=company_id, query=query)
            )
            if len(hits) >= _SEARCH_LIMIT:
                return hits[:_SEARCH_LIMIT]
        return hits

    async def _search_type(
        self,
        object_type: AuthzObjectType,
        *,
        company_id: str,
        query: str,
    ) -> list[AuthzExplorerObjectHit]:
        needle = query.strip()
        if object_type is AuthzObjectType.WIKI_PAGE:
            return await self._search_wiki(company_id, needle)
        if object_type is AuthzObjectType.CRM_ENTITY:
            return await self._search_crm(company_id, needle)
        if object_type is AuthzObjectType.OFFICE_DOCUMENT:
            return await self._search_office_documents(company_id, needle)
        if object_type is AuthzObjectType.OFFICE_CATALOG:
            return await self._search_office_catalogs(company_id, needle)
        if object_type is AuthzObjectType.FLOW:
            return await self._search_flows(company_id, needle)
        if object_type is AuthzObjectType.SYNC_CHANNEL:
            return await self._search_sync(company_id, needle)
        if object_type is AuthzObjectType.WORK_QUEUE:
            return await self._search_work_queues(company_id, needle)
        if object_type is AuthzObjectType.PLATFORM_NAMESPACE:
            return []
        if object_type is AuthzObjectType.CRM_NAMESPACE:
            return []
        return []

    async def _search_wiki(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._wiki()
        if db is None:
            return []
        stmt = select(WikiPageRow).where(
            WikiPageRow.company_id == company_id,
            WikiPageRow.deleted_at.is_(None),
        )
        if query != "":
            stmt = stmt.where(WikiPageRow.title.ilike(f"%{query}%"))
        stmt = stmt.order_by(WikiPageRow.title).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            title = row.title.strip()
            href, _manage = explorer_hrefs(
                AuthzObjectType.WIKI_PAGE, row.wiki_page_id, namespace=row.namespace
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.WIKI_PAGE,
                    object_key=row.wiki_page_id,
                    title=title if title != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=row.namespace,
                )
            )
        return hits

    async def _search_crm(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._crm()
        if db is None:
            return []
        stmt = select(CRMEntity).where(CRMEntity.company_id == company_id)
        if query != "":
            stmt = stmt.where(CRMEntity.name.ilike(f"%{query}%"))
        stmt = stmt.order_by(CRMEntity.name).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            name = row.name.strip()
            href, _manage = explorer_hrefs(
                AuthzObjectType.CRM_ENTITY, row.entity_id, namespace=row.namespace
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.CRM_ENTITY,
                    object_key=row.entity_id,
                    title=name if name != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=row.namespace,
                )
            )
        return hits

    async def _search_office_documents(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._office()
        if db is None:
            return []
        stmt = select(OfficeDocumentBinding).where(
            OfficeDocumentBinding.company_id == company_id,
            OfficeDocumentBinding.deleted_at.is_(None),
        )
        if query != "":
            stmt = stmt.where(OfficeDocumentBinding.title.ilike(f"%{query}%"))
        stmt = stmt.order_by(OfficeDocumentBinding.title).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            title = row.title.strip()
            href, _manage = explorer_hrefs(
                AuthzObjectType.OFFICE_DOCUMENT, row.file_id, namespace=row.namespace
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.OFFICE_DOCUMENT,
                    object_key=row.file_id,
                    title=title if title != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=row.namespace,
                )
            )
        return hits

    async def _search_office_catalogs(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._office()
        if db is None:
            return []
        stmt = select(OfficeDocumentCatalog).where(
            OfficeDocumentCatalog.company_id == company_id,
        )
        if query != "":
            stmt = stmt.where(OfficeDocumentCatalog.title.ilike(f"%{query}%"))
        stmt = stmt.order_by(OfficeDocumentCatalog.title).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            title = row.title.strip()
            href, _manage = explorer_hrefs(
                AuthzObjectType.OFFICE_CATALOG, row.catalog_id, namespace=row.namespace
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.OFFICE_CATALOG,
                    object_key=row.catalog_id,
                    title=title if title != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=row.namespace,
                )
            )
        return hits

    async def _search_flows(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        configs = await self._flow_repository.list(limit=_SEARCH_LIMIT, offset=0)
        hits: list[AuthzExplorerObjectHit] = []
        needle = query.casefold()
        for config in configs:
            name = config.name.strip()
            if needle != "" and needle not in name.casefold():
                continue
            object_key = format_namespace_key(company_id, config.flow_id)
            href, _manage = explorer_hrefs(
                AuthzObjectType.FLOW, object_key, namespace=None
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.FLOW,
                    object_key=object_key,
                    title=name if name != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=None,
                )
            )
        return hits

    async def _search_sync(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._sync()
        if db is None:
            return []
        stmt = select(SyncChannel).where(SyncChannel.company_id == company_id)
        if query != "":
            stmt = stmt.where(SyncChannel.name.ilike(f"%{query}%"))
        stmt = stmt.order_by(SyncChannel.name).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            raw_name = row.name
            title = raw_name.strip() if raw_name is not None else ""
            href, _manage = explorer_hrefs(
                AuthzObjectType.SYNC_CHANNEL, row.channel_id, namespace=row.namespace
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.SYNC_CHANNEL,
                    object_key=row.channel_id,
                    title=title if title != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if title != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=row.namespace,
                )
            )
        return hits

    async def _search_work_queues(
        self, company_id: str, query: str
    ) -> list[AuthzExplorerObjectHit]:
        db = self._worktracker()
        if db is None:
            return []
        stmt = select(WorkQueueRow).where(WorkQueueRow.company_id == company_id)
        if query != "":
            stmt = stmt.where(WorkQueueRow.name.ilike(f"%{query}%"))
        stmt = stmt.order_by(WorkQueueRow.name).limit(_SEARCH_LIMIT)
        async with db.session() as session:
            rows = list((await session.execute(stmt)).scalars().all())
        hits: list[AuthzExplorerObjectHit] = []
        for row in rows:
            name = row.name.strip()
            href, _manage = explorer_hrefs(
                AuthzObjectType.WORK_QUEUE, row.work_queue_id, namespace=None
            )
            hits.append(
                AuthzExplorerObjectHit(
                    object_type=AuthzObjectType.WORK_QUEUE,
                    object_key=row.work_queue_id,
                    title=name if name != "" else None,
                    title_status=(
                        AuthzTitleStatus.LOADED if name != "" else AuthzTitleStatus.MISSING
                    ),
                    href=href,
                    namespace=None,
                )
            )
        return hits
