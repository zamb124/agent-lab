"""`op_*` сервиса Search: один handler на verb, REST и WS RPC зовут одну функцию.

Crawl-администрирование и реестр индексов — платформенные операции компании `system`
(`require_system_admin`). Настройки провайдеров компании — админ активной компании.
Meta-поиск доступен любому пользователю, включая гостевую сессию публичного поиска.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from apps.search.config import (
    SearchLinkupConfig,
    SearchSerperConfig,
    SearchTavilyConfig,
    SearchTinyFishConfig,
    get_search_settings,
)
from apps.search.di import Di
from apps.search_worker.tasks.task_names import CRAWL_IMPORT_SEED_DOMAINS, CRAWL_ORCHESTRATOR_TICK
from core.ai.company_settings import encrypt_secret, mask_encrypted_secret
from core.company_search import (
    COMPANY_SEARCH_METADATA_KEY,
    CompanyLinkupSearchProvider,
    CompanySearchProviderBase,
    CompanySearchProviders,
    CompanySearchProvidersResponse,
    CompanySearchProviderView,
    CompanySerperSearchProvider,
    CompanyTavilySearchProvider,
    CompanyTinyFishSearchProvider,
    SearchCredentialSource,
    SearchProviderId,
)
from core.context import get_context
from core.crawl.models import (
    CrawlDomain,
    CrawlDomainCreateRequest,
    CrawlDomainPatchRequest,
    CrawlDomainRunResponse,
    CrawlJob,
    CrawlJobCreateRequest,
    CrawlJobQueuedResponse,
    CrawlProfileCreateRequest,
    CrawlProfilePatchRequest,
    CrawlProfileSummary,
    CrawlProfileWithIndex,
    CrawlUrl,
    CrawlUrlAddRequest,
    CrawlUrlDetail,
    CrawlUrlListItem,
    SeedImportRequest,
    SeedImportResult,
    UpsertStats,
)
from core.errors.boundary import PlatformNotFoundError
from core.models import StrictBaseModel
from core.models.identity_models import Company, User
from core.pagination import ListResponse, OffsetPage
from core.request_scope import require_company_admin, require_system_admin
from core.search.index_models import (
    SearchIndexBatchGetRequest,
    SearchIndexCreateRequest,
    SearchIndexDefinition,
    SearchIndexPatchRequest,
)
from core.search.logging_events import log_serp_click
from core.search.models import (
    MetaSearchRefineRequest,
    MetaSearchRequest,
    MetaSearchResponse,
    MetaSearchSerpMoreRequest,
    SearchProvidersSnapshot,
    SerpClickEvent,
)
from core.tasks import enqueue
from core.types import JsonObject
from core.websocket import EmptyPayload, raise_invalid, raise_not_found

# ---------------------------------------------------------------------------
# payloads
# ---------------------------------------------------------------------------


class SearchPagePayload(StrictBaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CrawlProfileIdPayload(StrictBaseModel):
    crawl_profile_id: str = Field(min_length=1)


class CrawlProfileUpdatePayload(CrawlProfilePatchRequest):
    crawl_profile_id: str = Field(min_length=1)


class CrawlProfileTrancoSeedRequest(StrictBaseModel):
    tranco_limit: int = Field(default=2000, ge=1, le=5000)


class CrawlProfileTrancoSeedPayload(CrawlProfileTrancoSeedRequest):
    crawl_profile_id: str = Field(min_length=1)


class CrawlJobsListPayload(SearchPagePayload):
    crawl_profile_id: str = Field(min_length=1)
    status: str | None = None


class CrawlJobIdPayload(StrictBaseModel):
    crawl_job_id: str = Field(min_length=1)


class CrawlDomainsListPayload(SearchPagePayload):
    crawl_profile_id: str = Field(min_length=1)
    status: str | None = None


class CrawlDomainCreatePayload(CrawlDomainCreateRequest):
    crawl_profile_id: str = Field(min_length=1)


class CrawlDomainRefPayload(StrictBaseModel):
    crawl_domain_id: str = Field(min_length=1)
    crawl_profile_id: str = Field(min_length=1)


class CrawlDomainUpdatePayload(CrawlDomainPatchRequest):
    crawl_domain_id: str = Field(min_length=1)
    crawl_profile_id: str = Field(min_length=1)


class CrawlDomainUrlsAddPayload(CrawlUrlAddRequest):
    crawl_domain_id: str = Field(min_length=1)
    crawl_profile_id: str = Field(min_length=1)


class CrawlUrlsListPayload(SearchPagePayload):
    crawl_profile_id: str = Field(min_length=1)
    crawl_status: str | None = None
    domain: str | None = None
    content_type: str | None = None
    primary_topic: str | None = None
    enriched_only: bool | None = None


class CrawlUrlRefPayload(StrictBaseModel):
    crawl_url_id: str = Field(min_length=1)
    crawl_profile_id: str = Field(min_length=1)


class SearchIndexesListPayload(SearchPagePayload):
    enabled: bool | None = None


class SearchIndexIdPayload(StrictBaseModel):
    search_index_id: str = Field(min_length=1)


class SearchIndexUpdatePayload(SearchIndexPatchRequest):
    search_index_id: str = Field(min_length=1)


class SearchProviderUpdateRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enabled: bool = True
    credential_source: SearchCredentialSource = "platform"
    api_key: str | None = None
    base_url: str | None = Field(default=None, min_length=1)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=60.0)
    depth: str | None = None
    search_depth: str | None = None
    topic: str | None = None
    include_answer: bool | None = None


class SearchProviderUpdatePayload(SearchProviderUpdateRequest):
    provider_id: SearchProviderId


class SearchProviderOrderPayload(StrictBaseModel):
    provider_order: list[SearchProviderId]


class SearchProviderIdPayload(StrictBaseModel):
    provider_id: SearchProviderId


class SearchOkResult(StrictBaseModel):
    success: bool = True


# ---------------------------------------------------------------------------
# crawl profiles
# ---------------------------------------------------------------------------


async def op_crawl_profiles_list(
    payload: SearchPagePayload, *, user: User, di: Di
) -> OffsetPage[CrawlProfileWithIndex]:
    _ = user
    _ = await require_system_admin(di.authz_service)
    return await di.crawl_service.list_profiles(limit=payload.limit, offset=payload.offset)


async def op_crawl_profiles_create(
    payload: CrawlProfileCreateRequest, *, user: User, di: Di
) -> CrawlProfileWithIndex:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_service.create_profile(payload)
    except ValueError as exc:
        raise_invalid(exc)


async def op_crawl_profiles_update(
    payload: CrawlProfileUpdatePayload, *, user: User, di: Di
) -> CrawlProfileWithIndex:
    _ = user
    _ = await require_system_admin(di.authz_service)
    patch = CrawlProfilePatchRequest.model_validate(payload.model_dump(exclude={"crawl_profile_id"}, exclude_unset=True))
    try:
        return await di.crawl_service.patch_profile(payload.crawl_profile_id, patch)
    except ValueError as exc:
        raise_invalid(exc)


async def op_crawl_profiles_summary(
    payload: CrawlProfileIdPayload, *, user: User, di: Di
) -> CrawlProfileSummary:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_report_service.get_profile_summary(payload.crawl_profile_id)
    except ValueError as exc:
        raise_not_found(exc)


async def op_crawl_profiles_tranco_seed(
    payload: CrawlProfileTrancoSeedPayload, *, user: User, di: Di
) -> SeedImportResult:
    _ = user
    _ = await require_system_admin(di.authz_service)
    _ = await enqueue(CRAWL_IMPORT_SEED_DOMAINS, payload.crawl_profile_id, "tranco", payload.tranco_limit)
    return SeedImportResult(imported=0, skipped=0)


# ---------------------------------------------------------------------------
# crawl jobs
# ---------------------------------------------------------------------------


async def op_crawl_jobs_queue(
    payload: CrawlJobCreateRequest, *, user: User, di: Di
) -> CrawlJobQueuedResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, payload.crawl_profile_id)
    return CrawlJobQueuedResponse(crawl_profile_id=payload.crawl_profile_id, status="queued")


async def op_crawl_jobs_list(
    payload: CrawlJobsListPayload, *, user: User, di: Di
) -> OffsetPage[CrawlJob]:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_report_service.list_jobs(
            crawl_profile_id=payload.crawl_profile_id,
            status=payload.status,
            limit=payload.limit,
            offset=payload.offset,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_crawl_jobs_get(payload: CrawlJobIdPayload, *, user: User, di: Di) -> CrawlJob:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_service.get_job(payload.crawl_job_id)
    except ValueError as exc:
        raise_not_found(exc)


# ---------------------------------------------------------------------------
# crawl domains
# ---------------------------------------------------------------------------


async def op_crawl_domains_list(
    payload: CrawlDomainsListPayload, *, user: User, di: Di
) -> OffsetPage[CrawlDomain]:
    _ = user
    _ = await require_system_admin(di.authz_service)
    return await di.crawl_report_service.list_domains(
        crawl_profile_id=payload.crawl_profile_id,
        status=payload.status,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_crawl_domains_create(
    payload: CrawlDomainCreatePayload, *, user: User, di: Di
) -> CrawlDomain:
    _ = user
    _ = await require_system_admin(di.authz_service)
    body = CrawlDomainCreateRequest.model_validate(payload.model_dump(exclude={"crawl_profile_id"}))
    try:
        domain = await di.crawl_service.create_domain(payload.crawl_profile_id, body)
    except ValueError as exc:
        raise_invalid(exc)
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, payload.crawl_profile_id)
    return domain


async def op_crawl_domains_update(
    payload: CrawlDomainUpdatePayload, *, user: User, di: Di
) -> CrawlDomain:
    _ = user
    _ = await require_system_admin(di.authz_service)
    patch = CrawlDomainPatchRequest.model_validate(
        payload.model_dump(exclude={"crawl_domain_id", "crawl_profile_id"}, exclude_unset=True)
    )
    try:
        return await di.crawl_service.patch_domain(payload.crawl_domain_id, payload.crawl_profile_id, patch)
    except ValueError as exc:
        raise_invalid(exc)


async def op_crawl_domains_remove(payload: CrawlDomainRefPayload, *, user: User, di: Di) -> None:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        await di.crawl_service.delete_domain(payload.crawl_domain_id, payload.crawl_profile_id)
    except ValueError as exc:
        raise_invalid(exc)


async def op_crawl_domains_run(
    payload: CrawlDomainRefPayload, *, user: User, di: Di
) -> CrawlDomainRunResponse:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_service.run_domain(payload.crawl_domain_id, payload.crawl_profile_id)
    except ValueError as exc:
        raise_invalid(exc)


async def op_crawl_domains_urls_add(
    payload: CrawlDomainUrlsAddPayload, *, user: User, di: Di
) -> UpsertStats:
    _ = user
    _ = await require_system_admin(di.authz_service)
    body = CrawlUrlAddRequest(urls=payload.urls)
    try:
        stats = await di.crawl_service.add_domain_urls(payload.crawl_domain_id, payload.crawl_profile_id, body)
    except ValueError as exc:
        raise_invalid(exc)
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, payload.crawl_profile_id)
    return stats


# ---------------------------------------------------------------------------
# crawl urls
# ---------------------------------------------------------------------------


async def op_crawl_urls_list(
    payload: CrawlUrlsListPayload, *, user: User, di: Di
) -> OffsetPage[CrawlUrlListItem]:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_report_service.list_urls(
            crawl_profile_id=payload.crawl_profile_id,
            crawl_status=payload.crawl_status,
            domain=payload.domain,
            content_type=payload.content_type,
            primary_topic=payload.primary_topic,
            enriched_only=payload.enriched_only,
            limit=payload.limit,
            offset=payload.offset,
        )
    except ValueError as exc:
        raise_not_found(exc)


async def op_crawl_urls_get(payload: CrawlUrlRefPayload, *, user: User, di: Di) -> CrawlUrlDetail:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.crawl_report_service.get_url_detail(payload.crawl_url_id, payload.crawl_profile_id)
    except ValueError as exc:
        raise_not_found(exc)


async def op_crawl_urls_recrawl(payload: CrawlUrlRefPayload, *, user: User, di: Di) -> CrawlUrl:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        crawl_url = await di.crawl_service.recrawl_url(payload.crawl_url_id, payload.crawl_profile_id)
    except ValueError as exc:
        raise_invalid(exc)
    _ = await enqueue(CRAWL_ORCHESTRATOR_TICK, payload.crawl_profile_id)
    return crawl_url


# ---------------------------------------------------------------------------
# crawl seed
# ---------------------------------------------------------------------------


async def op_crawl_seed_import(
    payload: SeedImportRequest, *, user: User, di: Di
) -> SeedImportResult:
    _ = user
    _ = await require_system_admin(di.authz_service)
    if payload.seed_source == "tranco":
        _ = await enqueue(CRAWL_IMPORT_SEED_DOMAINS, payload.crawl_profile_id, payload.seed_source, payload.tranco_limit)
        return SeedImportResult(imported=0, skipped=0)
    try:
        return await di.crawl_service.import_seed(payload)
    except ValueError as exc:
        raise_invalid(exc)


# ---------------------------------------------------------------------------
# search indexes
# ---------------------------------------------------------------------------


async def op_indexes_list(
    payload: SearchIndexesListPayload, *, user: User, di: Di
) -> OffsetPage[SearchIndexDefinition]:
    _ = user
    scope = await require_system_admin(di.authz_service)
    return await SearchIndexDefinition.page_by_search_index_id(
        company_id=scope.company_id,
        enabled=payload.enabled,
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_indexes_get(
    payload: SearchIndexIdPayload, *, user: User, di: Di
) -> SearchIndexDefinition:
    _ = user
    scope = await require_system_admin(di.authz_service)
    try:
        return await di.search_index_service.get(payload.search_index_id, company_id=scope.company_id)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)


async def op_indexes_create(
    payload: SearchIndexCreateRequest, *, user: User, di: Di
) -> SearchIndexDefinition:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        return await di.search_index_service.create(payload)
    except ValueError as exc:
        raise_invalid(exc)


async def op_indexes_update(
    payload: SearchIndexUpdatePayload, *, user: User, di: Di
) -> SearchIndexDefinition:
    _ = user
    _ = await require_system_admin(di.authz_service)
    patch = SearchIndexPatchRequest.model_validate(payload.model_dump(exclude={"search_index_id"}, exclude_unset=True))
    try:
        return await di.search_index_service.patch(payload.search_index_id, patch)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    except ValueError as exc:
        raise_invalid(exc)


async def op_indexes_batch_get(
    payload: SearchIndexBatchGetRequest, *, user: User, di: Di
) -> ListResponse[SearchIndexDefinition]:
    _ = user
    _ = await require_system_admin(di.authz_service)
    try:
        items = await di.search_index_service.batch_get(payload.search_index_ids)
    except PlatformNotFoundError as exc:
        raise_not_found(exc)
    return ListResponse[SearchIndexDefinition](items=items)


# ---------------------------------------------------------------------------
# meta search (доступен гостю публичного поиска)
# ---------------------------------------------------------------------------


async def op_query_search(payload: MetaSearchRequest, *, user: User, di: Di) -> MetaSearchResponse:
    _ = user
    context = get_context()
    company = context.active_company if context is not None else None
    user_id = context.user.user_id if context is not None else None
    try:
        return await di.meta_search_service.search(payload, company=company, user_id=user_id)
    except ValueError as exc:
        raise_invalid(exc)


async def op_query_serp_more(
    payload: MetaSearchSerpMoreRequest, *, user: User, di: Di
) -> MetaSearchResponse:
    _ = user
    try:
        return await di.meta_search_service.serp_more(payload)
    except ValueError as exc:
        raise_not_found(exc)


async def op_query_serp_refine(
    payload: MetaSearchRefineRequest, *, user: User, di: Di
) -> MetaSearchResponse:
    _ = user
    try:
        return await di.meta_search_service.refine(payload)
    except ValueError as exc:
        raise_not_found(exc)


async def op_query_serp_click(payload: SerpClickEvent, *, user: User, di: Di) -> None:
    _ = user, di
    log_serp_click(
        serp_cache_key=payload.serp_cache_key,
        query=payload.query,
        mode=payload.mode,
        url=payload.url,
        position=payload.position,
        provider=payload.provider,
        search_index_id=payload.search_index_id,
    )


async def op_query_providers_snapshot(
    payload: EmptyPayload, *, user: User, di: Di
) -> SearchProvidersSnapshot:
    _ = payload, user, di
    config = get_search_settings().search
    index_page = await SearchIndexDefinition.page_by_search_index_id(
        company_id="system",
        enabled=True,
        limit=100,
        offset=0,
    )
    return SearchProvidersSnapshot(
        provider_order=list(config.provider_order),
        index_enabled=config.index.enabled,
        default_index_ids=list(config.index.default_index_ids),
        search_index_ids=[item.search_index_id for item in index_page.items if item.search_enabled],
    )


# ---------------------------------------------------------------------------
# провайдеры компании (Company.metadata.search_providers)
# ---------------------------------------------------------------------------


_PROVIDER_IDS: tuple[SearchProviderId, ...] = ("tinyfish", "linkup", "serper", "tavily")


async def _load_company(company_id: str) -> Company:
    company = await Company.get(company_id)
    if company is None:
        raise PlatformNotFoundError(f"Company {company_id} not found", error_code='not_found')
    return company


def _company_settings(company: Company) -> CompanySearchProviders:
    try:
        return CompanySearchProviders.from_metadata(company.metadata)
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"company.metadata.search_providers is corrupt: {exc}") from exc


async def _save_company_settings(
    company: Company, settings: CompanySearchProviders
) -> None:
    metadata = dict(company.metadata)
    serialized = settings.to_metadata_dict()
    if serialized:
        metadata[COMPANY_SEARCH_METADATA_KEY] = serialized
    else:
        _ = metadata.pop(COMPANY_SEARCH_METADATA_KEY, None)
    company.metadata = metadata
    _ = await Company.set(company)


def _platform_provider_config(
    provider_id: SearchProviderId,
) -> SearchTinyFishConfig | SearchLinkupConfig | SearchSerperConfig | SearchTavilyConfig:
    platform_config = get_search_settings().search
    if provider_id == "tinyfish":
        return platform_config.tinyfish
    if provider_id == "linkup":
        return platform_config.linkup
    if provider_id == "serper":
        return platform_config.serper
    return platform_config.tavily


def _provider_view(provider_id: SearchProviderId, settings: CompanySearchProviders) -> CompanySearchProviderView:
    provider = settings.provider(provider_id)
    platform_provider = _platform_provider_config(provider_id)
    company_key = provider.credential_source == "company" and provider.api_key_encrypted is not None
    view = CompanySearchProviderView(
        provider_id=provider_id,
        enabled=provider.enabled,
        credential_source=provider.credential_source,
        configured=company_key,
        key_masked=mask_encrypted_secret(provider.api_key_encrypted) if company_key else None,
        base_url=provider.base_url,
        timeout_seconds=provider.timeout_seconds,
        platform_enabled=bool(platform_provider.enabled),
        platform_base_url=platform_provider.base_url,
        platform_key_configured=bool(platform_provider.api_key.strip()),
    )
    if isinstance(provider, CompanyLinkupSearchProvider):
        view.depth = provider.depth
    if isinstance(provider, CompanyTavilySearchProvider):
        view.search_depth = provider.search_depth
        view.topic = provider.topic
        view.include_answer = provider.include_answer
    return view


def _clean_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def _api_key_encrypted(payload: SearchProviderUpdatePayload, existing: CompanySearchProviderBase) -> str | None:
    if payload.credential_source == "platform":
        return None
    if payload.api_key is not None and payload.api_key.strip():
        return encrypt_secret(payload.api_key.strip())
    if existing.credential_source == "company" and existing.api_key_encrypted is not None:
        return existing.api_key_encrypted
    raise ValueError(
        f"API key is required for provider {payload.provider_id} when credential_source='company'"
    )


def _provider_override(
    payload: SearchProviderUpdatePayload, existing: CompanySearchProviderBase
) -> CompanySearchProviderBase:
    common: JsonObject = {
        "enabled": payload.enabled,
        "credential_source": payload.credential_source,
        "api_key_encrypted": _api_key_encrypted(payload, existing),
        "base_url": _clean_optional_string(payload.base_url),
        "timeout_seconds": payload.timeout_seconds,
    }
    if payload.provider_id == "tinyfish":
        return CompanyTinyFishSearchProvider.model_validate(common)
    if payload.provider_id == "serper":
        return CompanySerperSearchProvider.model_validate(common)
    if payload.provider_id == "linkup":
        depth = _clean_optional_string(payload.depth)
        if depth is not None:
            common["depth"] = depth
        return CompanyLinkupSearchProvider.model_validate(common)
    search_depth = _clean_optional_string(payload.search_depth)
    topic = _clean_optional_string(payload.topic)
    if search_depth is not None:
        common["search_depth"] = search_depth
    if topic is not None:
        common["topic"] = topic
    if payload.include_answer is not None:
        common["include_answer"] = payload.include_answer
    return CompanyTavilySearchProvider.model_validate(common)


async def op_providers_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> CompanySearchProvidersResponse:
    _ = payload, user
    scope = await require_company_admin(di.authz_service)
    company = await _load_company(scope.company_id)
    settings = _company_settings(company)
    return CompanySearchProvidersResponse(
        provider_order=list(settings.provider_order),
        providers=[_provider_view(provider_id, settings) for provider_id in _PROVIDER_IDS],
    )


async def op_providers_update(
    payload: SearchProviderUpdatePayload, *, user: User, di: Di
) -> SearchOkResult:
    _ = user
    scope = await require_company_admin(di.authz_service)
    company = await _load_company(scope.company_id)
    settings = _company_settings(company)
    try:
        override = _provider_override(payload, settings.provider(payload.provider_id))
        updated = CompanySearchProviders.model_validate(
            settings.model_copy(update={payload.provider_id: override}).model_dump(mode="json")
        )
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_company_settings(company, updated)
    return SearchOkResult()


async def op_providers_order_update(
    payload: SearchProviderOrderPayload, *, user: User, di: Di
) -> SearchOkResult:
    _ = user
    scope = await require_company_admin(di.authz_service)
    company = await _load_company(scope.company_id)
    settings = _company_settings(company)
    try:
        updated = CompanySearchProviders.model_validate(
            settings.model_copy(update={"provider_order": payload.provider_order}).model_dump(mode="json")
        )
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_company_settings(company, updated)
    return SearchOkResult()


async def op_providers_reset(
    payload: SearchProviderIdPayload, *, user: User, di: Di
) -> SearchOkResult:
    _ = user
    scope = await require_company_admin(di.authz_service)
    company = await _load_company(scope.company_id)
    settings = _company_settings(company)
    defaults = CompanySearchProviders()
    try:
        updated = CompanySearchProviders.model_validate(
            settings.model_copy(update={payload.provider_id: defaults.provider(payload.provider_id)}).model_dump(mode="json")
        )
    except (ValueError, ValidationError) as exc:
        raise_invalid(exc)
    await _save_company_settings(company, updated)
    return SearchOkResult()
