"""Гидрация title/href для Access Explorer через репозитории владельцев объектов.

Frontend читает peer-БД только через репозитории сервисов-владельцев (architecture.mdc
«Репозиторий приоритетнее»): SQL и ORM здесь не появляются. Репозиторий отсутствует,
если URL БД домена не настроен — тогда объекты домена гидрируются как `UNAVAILABLE`.
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.crm.db.repositories.entity_repository import EntityRepository
from apps.flows.src.db.flow_repository import FlowRepository
from apps.office.db.repositories.catalog_repository import CatalogRepository
from apps.office.db.repositories.document_binding_repository import DocumentBindingRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.wiki.db.repositories.wiki_repository import WikiRepository
from core.authz.explorer import AuthzExplorerObjectHit, AuthzTitleStatus
from core.authz.ids import format_namespace_key, parse_flow_branch_key, parse_namespace_key
from core.authz.types import AuthzObjectType
from core.mail.repositories import MailboxBindingRepository
from core.worktracker.repository import WorktrackerRepository

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


@dataclass(frozen=True, slots=True)
class AuthzExplorerRepositories:
    """Репозитории владельцев; `None` — БД домена не настроена в этом процессе."""

    flow: FlowRepository
    mailbox_binding: MailboxBindingRepository
    worktracker: WorktrackerRepository | None
    wiki: WikiRepository | None
    crm_entity: EntityRepository | None
    office_catalog: CatalogRepository | None
    office_binding: DocumentBindingRepository | None
    sync_channel: ChannelRepository | None


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


def _title_status(title: str | None) -> AuthzTitleStatus:
    return AuthzTitleStatus.LOADED if title else AuthzTitleStatus.MISSING


def _clean_title(raw: str | None) -> str | None:
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped if stripped != "" else None


def _hydrated(
    object_type: AuthzObjectType,
    object_key: str,
    *,
    title: str | None,
    status: AuthzTitleStatus,
    namespace: str | None,
    company_id: str | None,
) -> AuthzHydratedObject:
    href, manage_href = explorer_hrefs(object_type, object_key, namespace=namespace)
    return AuthzHydratedObject(
        object_type=object_type,
        object_key=object_key,
        title=title,
        title_status=status,
        href=href,
        manage_href=manage_href,
        namespace=namespace,
        company_id=company_id,
    )


def _missing(object_type: AuthzObjectType, object_key: str) -> AuthzHydratedObject:
    return _hydrated(object_type, object_key, title=None, status=AuthzTitleStatus.MISSING, namespace=None, company_id=None)


def _unavailable(object_type: AuthzObjectType, object_key: str) -> AuthzHydratedObject:
    return _hydrated(
        object_type, object_key, title=None, status=AuthzTitleStatus.UNAVAILABLE, namespace=None, company_id=None
    )


def _hit(object_type: AuthzObjectType, object_key: str, title: str | None, namespace: str | None) -> AuthzExplorerObjectHit:
    href, _manage = explorer_hrefs(object_type, object_key, namespace=namespace)
    return AuthzExplorerObjectHit(
        object_type=object_type,
        object_key=object_key,
        title=title,
        title_status=_title_status(title),
        href=href,
        namespace=namespace,
    )


class AuthzExplorerHydrator:
    def __init__(self, repositories: AuthzExplorerRepositories) -> None:
        self._repositories: AuthzExplorerRepositories = repositories

    async def hydrate(
        self,
        object_type: AuthzObjectType,
        object_key: str,
        *,
        company_id: str,
    ) -> AuthzHydratedObject:
        if object_type in (AuthzObjectType.PLATFORM_NAMESPACE, AuthzObjectType.CRM_NAMESPACE):
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
        return _missing(object_type, object_key)

    def _hydrate_namespace(
        self, object_type: AuthzObjectType, object_key: str, company_id: str
    ) -> AuthzHydratedObject:
        key_company_id, namespace = parse_namespace_key(object_key)
        matched = key_company_id == company_id
        return _hydrated(
            object_type,
            object_key,
            title=namespace if matched else None,
            status=AuthzTitleStatus.LOADED if matched else AuthzTitleStatus.MISSING,
            namespace=namespace,
            company_id=key_company_id,
        )

    async def _hydrate_wiki_page(self, wiki_page_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.wiki
        if repository is None:
            return _unavailable(AuthzObjectType.WIKI_PAGE, wiki_page_id)
        page = await repository.find_summary_in_company(company_id, wiki_page_id)
        if page is None:
            return _missing(AuthzObjectType.WIKI_PAGE, wiki_page_id)
        title = _clean_title(page.title)
        return _hydrated(
            AuthzObjectType.WIKI_PAGE,
            wiki_page_id,
            title=title,
            status=_title_status(title),
            namespace=page.namespace,
            company_id=company_id,
        )

    async def _hydrate_crm_entity(self, entity_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.crm_entity
        if repository is None:
            return _unavailable(AuthzObjectType.CRM_ENTITY, entity_id)
        entity = await repository.get_in_company(entity_id, company_id)
        if entity is None:
            return _missing(AuthzObjectType.CRM_ENTITY, entity_id)
        title = _clean_title(entity.name)
        return _hydrated(
            AuthzObjectType.CRM_ENTITY,
            entity_id,
            title=title,
            status=_title_status(title),
            namespace=entity.namespace,
            company_id=entity.company_id,
        )

    async def _hydrate_office_catalog(self, catalog_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.office_catalog
        if repository is None:
            return _unavailable(AuthzObjectType.OFFICE_CATALOG, catalog_id)
        catalog = await repository.get_in_company(catalog_id, company_id)
        if catalog is None:
            return _missing(AuthzObjectType.OFFICE_CATALOG, catalog_id)
        title = _clean_title(catalog.title)
        return _hydrated(
            AuthzObjectType.OFFICE_CATALOG,
            catalog_id,
            title=title,
            status=_title_status(title),
            namespace=catalog.namespace,
            company_id=catalog.company_id,
        )

    async def _hydrate_office_document(self, file_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.office_binding
        if repository is None:
            return _unavailable(AuthzObjectType.OFFICE_DOCUMENT, file_id)
        binding = await repository.get_by_file_and_company(file_id, company_id)
        if binding is None or binding.deleted_at is not None:
            return _missing(AuthzObjectType.OFFICE_DOCUMENT, file_id)
        title = _clean_title(binding.title)
        return _hydrated(
            AuthzObjectType.OFFICE_DOCUMENT,
            file_id,
            title=title,
            status=_title_status(title),
            namespace=binding.namespace,
            company_id=binding.company_id,
        )

    async def _hydrate_flow(self, object_key: str, company_id: str) -> AuthzHydratedObject:
        key_company_id, flow_id = parse_namespace_key(object_key)
        if key_company_id != company_id:
            return _missing(AuthzObjectType.FLOW, object_key)
        config = await self._repositories.flow.get_latest(flow_id)
        if config is None:
            return _missing(AuthzObjectType.FLOW, object_key)
        title = _clean_title(config.name)
        return _hydrated(
            AuthzObjectType.FLOW,
            object_key,
            title=title,
            status=_title_status(title),
            namespace=None,
            company_id=company_id,
        )

    def _hydrate_flow_branch(self, object_key: str, company_id: str) -> AuthzHydratedObject:
        key_company_id, _flow_id, _branch_id = parse_flow_branch_key(object_key)
        return _hydrated(
            AuthzObjectType.FLOW_BRANCH,
            object_key,
            title=None,
            status=AuthzTitleStatus.MISSING,
            namespace=None,
            company_id=company_id if key_company_id == company_id else None,
        )

    def _hydrate_tool(self, object_key: str, company_id: str) -> AuthzHydratedObject:
        key_company_id, _tool_id = parse_namespace_key(object_key)
        return _hydrated(
            AuthzObjectType.TOOL,
            object_key,
            title=None,
            status=AuthzTitleStatus.MISSING,
            namespace=None,
            company_id=company_id if key_company_id == company_id else None,
        )

    async def _hydrate_sync_channel(self, channel_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.sync_channel
        if repository is None:
            return _unavailable(AuthzObjectType.SYNC_CHANNEL, channel_id)
        channel = await repository.get_in_company(channel_id, company_id)
        if channel is None:
            return _missing(AuthzObjectType.SYNC_CHANNEL, channel_id)
        title = _clean_title(channel.name)
        return _hydrated(
            AuthzObjectType.SYNC_CHANNEL,
            channel_id,
            title=title,
            status=_title_status(title),
            namespace=channel.namespace,
            company_id=channel.company_id,
        )

    async def _hydrate_work_queue(self, work_queue_id: str, company_id: str) -> AuthzHydratedObject:
        repository = self._repositories.worktracker
        if repository is None:
            return _unavailable(AuthzObjectType.WORK_QUEUE, work_queue_id)
        queue = await repository.get_queue(company_id, work_queue_id)
        if queue is None:
            return _missing(AuthzObjectType.WORK_QUEUE, work_queue_id)
        title = _clean_title(queue.name)
        return _hydrated(
            AuthzObjectType.WORK_QUEUE,
            work_queue_id,
            title=title,
            status=_title_status(title),
            namespace=None,
            company_id=queue.company_id,
        )

    async def _hydrate_mailbox(self, mailbox_binding_id: str, company_id: str) -> AuthzHydratedObject:
        binding = await self._repositories.mailbox_binding.get(mailbox_binding_id, company_id)
        if binding is None:
            return _missing(AuthzObjectType.MAILBOX_BINDING, mailbox_binding_id)
        return _hydrated(
            AuthzObjectType.MAILBOX_BINDING,
            mailbox_binding_id,
            title=binding.email_address,
            status=AuthzTitleStatus.LOADED,
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
            hits.extend(await self._search_type(search_type, company_id=company_id, query=query.strip()))
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
        if object_type is AuthzObjectType.WIKI_PAGE:
            return await self._search_wiki(company_id, query)
        if object_type is AuthzObjectType.CRM_ENTITY:
            return await self._search_crm(company_id, query)
        if object_type is AuthzObjectType.OFFICE_DOCUMENT:
            return await self._search_office_documents(company_id, query)
        if object_type is AuthzObjectType.OFFICE_CATALOG:
            return await self._search_office_catalogs(company_id, query)
        if object_type is AuthzObjectType.FLOW:
            return await self._search_flows(company_id, query)
        if object_type is AuthzObjectType.SYNC_CHANNEL:
            return await self._search_sync(company_id, query)
        if object_type is AuthzObjectType.WORK_QUEUE:
            return await self._search_work_queues(company_id, query)
        return []

    async def _search_wiki(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.wiki
        if repository is None:
            return []
        pages = await repository.search_summaries_in_company(company_id, query, limit=_SEARCH_LIMIT)
        return [
            _hit(AuthzObjectType.WIKI_PAGE, page.wiki_page_id, _clean_title(page.title), page.namespace)
            for page in pages
        ]

    async def _search_crm(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.crm_entity
        if repository is None:
            return []
        entities = await repository.search_by_name_in_company(company_id, query, limit=_SEARCH_LIMIT)
        return [
            _hit(AuthzObjectType.CRM_ENTITY, entity.entity_id, _clean_title(entity.name), entity.namespace)
            for entity in entities
        ]

    async def _search_office_documents(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.office_binding
        if repository is None:
            return []
        bindings = await repository.search_titles_in_company(company_id, query, limit=_SEARCH_LIMIT)
        return [
            _hit(AuthzObjectType.OFFICE_DOCUMENT, binding.file_id, _clean_title(binding.title), binding.namespace)
            for binding in bindings
        ]

    async def _search_office_catalogs(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.office_catalog
        if repository is None:
            return []
        catalogs = await repository.search_titles_in_company(company_id, query, limit=_SEARCH_LIMIT)
        return [
            _hit(AuthzObjectType.OFFICE_CATALOG, catalog.catalog_id, _clean_title(catalog.title), catalog.namespace)
            for catalog in catalogs
        ]

    async def _search_flows(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        configs = await self._repositories.flow.list(limit=_SEARCH_LIMIT, offset=0)
        needle = query.casefold()
        hits: list[AuthzExplorerObjectHit] = []
        for config in configs:
            title = _clean_title(config.name)
            if needle != "" and needle not in (title or "").casefold():
                continue
            hits.append(_hit(AuthzObjectType.FLOW, format_namespace_key(company_id, config.flow_id), title, None))
        return hits

    async def _search_sync(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.sync_channel
        if repository is None:
            return []
        channels = await repository.search_by_name_in_company(company_id, query, limit=_SEARCH_LIMIT)
        return [
            _hit(AuthzObjectType.SYNC_CHANNEL, channel.channel_id, _clean_title(channel.name), channel.namespace)
            for channel in channels
        ]

    async def _search_work_queues(self, company_id: str, query: str) -> list[AuthzExplorerObjectHit]:
        repository = self._repositories.worktracker
        if repository is None:
            return []
        needle = query.casefold()
        hits: list[AuthzExplorerObjectHit] = []
        for queue in await repository.list_queues(company_id):
            title = _clean_title(queue.name)
            if needle != "" and needle not in (title or "").casefold():
                continue
            hits.append(_hit(AuthzObjectType.WORK_QUEUE, queue.work_queue_id, title, None))
            if len(hits) >= _SEARCH_LIMIT:
                break
        return hits
