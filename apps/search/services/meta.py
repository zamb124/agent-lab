"""Meta-search orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from apps.search.config import SearchIntegrationConfig
from apps.search.providers import (
    LinkupSearchProvider,
    SearchProvider,
    SerperSearchProvider,
    TavilySearchProvider,
    TinyFishSearchProvider,
)
from apps.search.providers.index import IndexSearchProvider
from apps.search.services.company_config import (
    ResolvedSearchConfig,
    resolve_search_config_for_company,
)
from apps.search.services.index_resolver import preprocess_meta_search_request
from apps.search.services.provider_availability import ProviderAvailabilityStore
from apps.search.services.serp_cache import SerpCacheMissError, SerpCacheService
from core.ai.runtime import rerank_scores
from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.service import BALANCE_BLOCK_OPERATION_SEARCH, BillingService
from core.config import get_settings
from core.models.billing_models import UsageType
from core.models.identity_models import Company
from core.rag.post_retrieval_rerank import rerank_options
from core.search import (
    PUBLIC_SEARCH_WALL_TIME_SECONDS,
    MetaSearchProviderStatus,
    MetaSearchRefineRequest,
    MetaSearchRequest,
    MetaSearchResponse,
    MetaSearchSerpMoreRequest,
    WebSearchResult,
)
from core.search.logging_events import log_serp_served
from core.tracing import attributes as trace_attr
from core.tracing.operation_span import traced_operation

_PROVIDER_ALIASES: dict[str, str] = {
    "auto": "auto",
    "google": "serper",
    "tiny": "tinyfish",
    "tinyfish": "tinyfish",
    "linkup": "linkup",
    "serper_google": "serper",
    "serper": "serper",
    "tavily": "tavily",
    "travily": "tavily",
    "runet": "index",
    "index": "index",
}

_TRACKING_QUERY_PARAMS = {
    "fbclid",
    "gclid",
    "yclid",
    "mc_cid",
    "mc_eid",
}

ProviderSearchOutcome = tuple[list[WebSearchResult], MetaSearchProviderStatus]

_INDEX_EMPTY_RESULTS_ERROR = "index returned no results"


def _should_mark_provider_unavailable(provider_id: str, error: str) -> bool:
    if provider_id == "index" and error == _INDEX_EMPTY_RESULTS_ERROR:
        return False
    return True


def _canonical_url(url: str) -> str:
    try:
        parsed = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING_QUERY_PARAMS
    ]
    path = parsed.path.rstrip("/") or parsed.path
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(query),
            "",
        )
    )


def _rank_results(
    candidates: dict[str, WebSearchResult],
    scores: dict[str, float],
    limit: int,
) -> list[WebSearchResult]:
    ordered = sorted(
        candidates.items(),
        key=lambda item: (-scores[item[0]], item[1].provider_rank, item[1].title),
    )
    out: list[WebSearchResult] = []
    for rank, (key, result) in enumerate(ordered[:limit], start=1):
        out.append(result.model_copy(update={"rank": rank, "score": round(scores[key], 6)}))
    return out


class MetaSearchService:
    """Small provider router with deterministic dedupe and ranking."""

    def __init__(
        self,
        search_config: SearchIntegrationConfig,
        availability_store: ProviderAvailabilityStore,
        billing_service: BillingService,
        index_provider: IndexSearchProvider,
        serp_cache_service: SerpCacheService,
    ) -> None:
        self._config: SearchIntegrationConfig = search_config
        self._availability_store: ProviderAvailabilityStore = availability_store
        self._billing_service: BillingService = billing_service
        self._index_provider: IndexSearchProvider = index_provider
        self._serp_cache_service: SerpCacheService = serp_cache_service

    async def serp_more(self, body: MetaSearchSerpMoreRequest) -> MetaSearchResponse:
        try:
            page_items, total_count, has_more, query = await self._serp_cache_service.slice(
                body.serp_cache_key,
                offset=body.offset,
                limit=body.limit,
            )
        except SerpCacheMissError as exc:
            raise ValueError(str(exc)) from exc
        return MetaSearchResponse(
            query=query,
            results=page_items,
            providers={},
            total_count=total_count,
            has_more=has_more,
            offset=body.offset,
            limit=body.limit,
            serp_cache_key=body.serp_cache_key,
        )

    async def refine(self, body: MetaSearchRefineRequest) -> MetaSearchResponse:
        """Доранжирует закэшированный preview-пул реранкером и отдаёт refined-страницу."""
        try:
            entry = await self._serp_cache_service.load_entry(body.serp_cache_key)
        except SerpCacheMissError as exc:
            raise ValueError(str(exc)) from exc
        reranked_pool = await self._rerank_serp_pool(query=body.query, pool=entry.ranked)
        serp_cache_key = await self._serp_cache_service.store_pool(
            query=entry.query,
            mode=entry.mode,
            index_ids=entry.index_ids,
            ranked=reranked_pool,
        )
        total_count = len(reranked_pool)
        page_items = reranked_pool[body.offset : body.offset + body.limit]
        ranked_page: list[WebSearchResult] = []
        for rank, item in enumerate(page_items, start=body.offset + 1):
            ranked_page.append(item.model_copy(update={"rank": rank}))
        has_more = body.offset + len(page_items) < total_count
        return MetaSearchResponse(
            query=entry.query,
            results=ranked_page,
            providers={},
            total_count=total_count,
            has_more=has_more,
            offset=body.offset,
            limit=body.limit,
            serp_cache_key=serp_cache_key,
            rank_stage="refined",
        )

    async def _rerank_serp_pool(
        self,
        *,
        query: str,
        pool: list[WebSearchResult],
    ) -> list[WebSearchResult]:
        if not pool:
            return list(pool)
        settings = get_settings()
        resolution = rerank_options(None, None, settings)
        if not resolution.enabled or resolution.url is None:
            raise ValueError("serp refine: reranker is not configured")
        rr = settings.rag.reranker
        passages = [f"{item.title}\n{item.snippet}".strip() for item in pool]
        async with traced_operation(
            "search.serp.refine",
            event_type="search.serp.refine",
            operation_category="search",
            extra_attributes={
                "platform.search.refine_pool_size": len(pool),
            },
        ) as span:
            scores = await rerank_scores(
                endpoint_url=resolution.url,
                query=query,
                passages=passages,
                timeout_seconds=PUBLIC_SEARCH_WALL_TIME_SECONDS,
                cost_per_1m_tokens=rr.cost_per_1m_tokens,
                platform_markup=rr.platform_markup,
                billing_resource_id=resolution.billing_resource_id or resolution.model or rr.billing_model_id,
                cost_origin="platform",
                model=resolution.model,
                api_key=resolution.api_key,
                extra_request_headers=resolution.extra_request_headers,
            )
            span.set_attribute("platform.search.refine_scored", len(scores))
        ordered = sorted(
            zip(pool, scores, strict=True),
            key=lambda pair: pair[1],
            reverse=True,
        )
        reranked: list[WebSearchResult] = []
        for rank, (item, score) in enumerate(ordered, start=1):
            reranked.append(item.model_copy(update={"rank": rank, "score": round(float(score), 6)}))
        return reranked

    async def search(
        self,
        request: MetaSearchRequest,
        *,
        company: Company | None = None,
        user_id: str | None = None,
    ) -> MetaSearchResponse:
        preprocessed = preprocess_meta_search_request(request, self._config.index)
        request = preprocessed.request
        resolved = resolve_search_config_for_company(
            platform_config=self._config,
            company=company,
        )
        providers = self._providers(resolved.config)
        provider_ids = self._resolve_provider_sequence(request.providers, resolved.config)
        scope_id = self._availability_scope(company)
        if request.provider_strategy == "first_available":
            return await self._search_first_available(
                request,
                provider_ids,
                providers,
                resolved,
                scope_id,
                company,
                user_id,
                preprocessed.index_ids,
            )
        return await self._search_merge(
            request,
            provider_ids,
            providers,
            resolved,
            scope_id,
            company,
            user_id,
            preprocessed.index_ids,
        )

    async def _search_first_available(
        self,
        request: MetaSearchRequest,
        provider_ids: list[str],
        providers: dict[str, SearchProvider],
        resolved: ResolvedSearchConfig,
        scope_id: str,
        company: Company | None,
        user_id: str | None,
        index_ids: list[str],
    ) -> MetaSearchResponse:
        statuses: dict[str, MetaSearchProviderStatus] = {}
        for provider_id in provider_ids:
            if provider_id not in providers:
                statuses[provider_id] = self._unsupported_status(provider_id)
                continue
            unavailable_status = await self._unavailable_skip_status(provider_id, scope_id, resolved)
            if unavailable_status is not None:
                statuses[provider_id] = unavailable_status
                continue

            provider = providers[provider_id]
            balance_status = await self._billable_operation_status(
                provider_id,
                resolved,
                company,
                user_id,
            )
            if balance_status is not None:
                statuses[provider_id] = balance_status
                continue
            results, status = await self._search_provider(
                provider_id,
                provider,
                request,
                resolved,
                company,
                index_ids,
            )
            status = status.model_copy(update={"selected": True})
            statuses[provider_id] = status
            if status.ok:
                _ = await self._availability_store.mark_available(provider_id, scope_id=scope_id)
                ranked_pool = self._normalize_ranked_pool(results)
                return await self._finalize_paged_response(
                    request,
                    ranked_pool,
                    statuses,
                    index_ids,
                )
            provider_error = status.error or "unknown error"
            if _should_mark_provider_unavailable(provider_id, provider_error):
                _ = await self._availability_store.mark_unavailable(
                    provider_id,
                    provider_error,
                    scope_id=scope_id,
                )

        return MetaSearchResponse(
            query=request.query,
            results=[],
            providers=statuses,
            total_count=0,
            has_more=False,
            offset=request.offset,
            limit=request.limit,
        )

    async def _search_merge(
        self,
        request: MetaSearchRequest,
        provider_ids: list[str],
        providers: dict[str, SearchProvider],
        resolved: ResolvedSearchConfig,
        scope_id: str,
        company: Company | None,
        user_id: str | None,
        index_ids: list[str],
    ) -> MetaSearchResponse:
        statuses: dict[str, MetaSearchProviderStatus] = {}
        tasks: list[tuple[str, Awaitable[ProviderSearchOutcome]]] = []
        for provider_id in provider_ids:
            if provider_id not in providers:
                statuses[provider_id] = self._unsupported_status(provider_id)
                continue
            unavailable_status = await self._unavailable_skip_status(provider_id, scope_id, resolved)
            if unavailable_status is not None:
                statuses[provider_id] = unavailable_status
                continue
            balance_status = await self._billable_operation_status(
                provider_id,
                resolved,
                company,
                user_id,
            )
            if balance_status is not None:
                statuses[provider_id] = balance_status
                continue
            provider = providers[provider_id]
            tasks.append(
                (
                    provider_id,
                    self._search_provider(provider_id, provider, request, resolved, company, index_ids),
                )
            )

        provider_results: list[tuple[str, list[WebSearchResult]]] = []
        if tasks:
            gathered = await asyncio.gather(*(task for _, task in tasks))
            for (provider_id, _), (results, status) in zip(tasks, gathered, strict=True):
                selected_status = status.model_copy(update={"selected": True})
                statuses[provider_id] = selected_status
                if selected_status.ok:
                    _ = await self._availability_store.mark_available(provider_id, scope_id=scope_id)
                    provider_results.append((provider_id, results))
                else:
                    provider_error = selected_status.error or "unknown error"
                    if _should_mark_provider_unavailable(provider_id, provider_error):
                        _ = await self._availability_store.mark_unavailable(
                            provider_id,
                            provider_error,
                            scope_id=scope_id,
                        )

        pool_limit = self._resolve_pool_limit(request)
        ranked_pool = self._collect_ranked(provider_results, pool_limit)
        return await self._finalize_paged_response(
            request,
            ranked_pool,
            statuses,
            index_ids,
        )

    def _resolve_pool_limit(self, request: MetaSearchRequest) -> int:
        if request.retrieve_limit is not None:
            return request.retrieve_limit
        return request.limit

    def _normalize_ranked_pool(self, results: list[WebSearchResult]) -> list[WebSearchResult]:
        normalized: list[WebSearchResult] = []
        for rank, item in enumerate(results, start=1):
            normalized.append(item.model_copy(update={"rank": rank, "provider_rank": rank}))
        return normalized

    async def _finalize_paged_response(
        self,
        request: MetaSearchRequest,
        ranked_pool: list[WebSearchResult],
        statuses: dict[str, MetaSearchProviderStatus],
        index_ids: list[str],
    ) -> MetaSearchResponse:
        total_count = len(ranked_pool)
        serp_cache_key: str | None = None
        # quick staged поиск всегда кэширует пул, чтобы refine мог доранжировать
        # его реранкером даже когда total_count <= limit.
        should_cache_pool = total_count > 0 and (
            total_count > request.limit or request.mode == "quick"
        )
        if should_cache_pool:
            serp_cache_key = await self._serp_cache_service.store_pool(
                query=request.query,
                mode=request.mode,
                index_ids=index_ids,
                ranked=ranked_pool,
            )
        page_start = request.offset
        page_end = request.offset + request.limit
        page_items = ranked_pool[page_start:page_end]
        ranked_page: list[WebSearchResult] = []
        for rank, item in enumerate(page_items, start=page_start + 1):
            ranked_page.append(item.model_copy(update={"rank": rank}))
        has_more = page_end < total_count and serp_cache_key is not None
        log_serp_served(
            query=request.query,
            mode=request.mode,
            serp_cache_key=serp_cache_key if serp_cache_key is not None else "",
            results_count=len(ranked_page),
            total_count=total_count,
            providers_selected=[name for name, status in statuses.items() if status.selected],
        )
        return MetaSearchResponse(
            query=request.query,
            results=ranked_page,
            providers=statuses,
            total_count=total_count,
            has_more=has_more,
            offset=request.offset,
            limit=request.limit,
            serp_cache_key=serp_cache_key,
        )

    async def _unavailable_skip_status(
        self,
        provider_id: str,
        scope_id: str,
        resolved: ResolvedSearchConfig,
    ) -> MetaSearchProviderStatus | None:
        record = await self._availability_store.get(provider_id, scope_id=scope_id)
        if record is None or record.available:
            return None
        return MetaSearchProviderStatus(
            ok=False,
            error=record.last_error,
            skipped=True,
            skip_reason="provider marked unavailable in redis",
            credential_source=resolved.credential_source(provider_id),
            billing_resource_name=f"search:{provider_id}",
        )

    async def _billable_operation_status(
        self,
        provider_id: str,
        resolved: ResolvedSearchConfig,
        company: Company | None,
        user_id: str | None,
    ) -> MetaSearchProviderStatus | None:
        if company is None or company.company_id == "system":
            return None
        credential_source = resolved.credential_source(provider_id)
        if credential_source == "company":
            return None
        if user_id is None or not user_id.strip():
            return MetaSearchProviderStatus(
                ok=False,
                error="user_id is required for platform-billed search",
                skipped=True,
                skip_reason="billing context is incomplete",
                credential_source=credential_source,
                billing_resource_name=f"search:{provider_id}",
            )
        try:
            await self._billing_service.require_balance_for_billable_operation(
                company.company_id,
                user_id,
                operation_code=BALANCE_BLOCK_OPERATION_SEARCH,
                notification_service="frontend",
                cost_origin="platform",
            )
        except BillingBalanceBlockedError as exc:
            return MetaSearchProviderStatus(
                ok=False,
                error=str(exc),
                skipped=True,
                skip_reason="billing balance blocked",
                credential_source=credential_source,
                billing_resource_name=f"search:{provider_id}",
            )
        return None

    async def _search_provider(
        self,
        provider_id: str,
        provider: SearchProvider,
        request: MetaSearchRequest,
        resolved: ResolvedSearchConfig,
        company: Company | None,
        _index_ids: list[str],
    ) -> ProviderSearchOutcome:
        credential_source = resolved.credential_source(provider_id)
        billing_resource_name = f"search:{provider_id}"
        async with traced_operation(
            f"search.provider.{provider_id}",
            event_type="search.provider.call",
            operation_category="search",
            billing_resource_name=billing_resource_name,
            billing_quantity=1,
            billing_cost_origin=credential_source,
            extra_attributes={
                "platform.search.provider_id": provider_id,
                "platform.search.credential_source": credential_source,
            },
        ) as span:
            if provider_id == "index":
                results, status = await self._index_provider.search(request)
            else:
                results, status = await provider.search(request)
            status = status.model_copy(
                update={
                    "credential_source": credential_source,
                    "billing_resource_name": billing_resource_name,
                }
            )
            span.set_attribute("platform.search.result_count", status.results_count)
            span.set_attribute("platform.search.ok", status.ok)
            if status.error:
                span.set_attribute("platform.search.error", status.error[:500])
            if status.ok and company is not None and company.company_id != "system":
                span.set_attribute(trace_attr.ATTR_BILLING_USAGE_TYPE, UsageType.TOOL_CALL.value)
                span.set_attribute(trace_attr.ATTR_BILLING_PENDING_SETTLEMENT, True)
            return results, status

    def _providers(self, config: SearchIntegrationConfig) -> dict[str, SearchProvider]:
        return {
            "index": self._index_provider,
            "tinyfish": TinyFishSearchProvider(config.tinyfish),
            "linkup": LinkupSearchProvider(config.linkup),
            "serper": SerperSearchProvider(config.serper),
            "tavily": TavilySearchProvider(config.tavily),
        }

    def _collect_ranked(
        self,
        provider_results: list[tuple[str, list[WebSearchResult]]],
        limit: int,
    ) -> list[WebSearchResult]:
        candidates: dict[str, WebSearchResult] = {}
        scores: dict[str, float] = {}
        for _, results in provider_results:
            for result in results:
                key = _canonical_url(result.url)
                score = 1.0 / (60.0 + float(result.provider_rank))
                if key not in candidates:
                    candidates[key] = result
                    scores[key] = score
                    continue
                scores[key] += score
                existing = candidates[key]
                if result.snippet and not existing.snippet:
                    candidates[key] = result
        return _rank_results(candidates, scores, limit)

    def _resolve_provider_sequence(
        self,
        raw: list[str],
        config: SearchIntegrationConfig,
    ) -> list[str]:
        provider_ids = self._normalize_provider_ids(raw)
        if "auto" not in provider_ids:
            return provider_ids
        out: list[str] = []
        for provider_id in config.provider_order:
            if provider_id and provider_id not in out:
                out.append(provider_id)
        for provider_id in provider_ids:
            if provider_id != "auto" and provider_id not in out:
                out.append(provider_id)
        return out

    def _normalize_provider_ids(self, raw: list[str]) -> list[str]:
        out: list[str] = []
        for item in raw:
            raw_provider_id = item.strip().lower()
            provider_id = (
                _PROVIDER_ALIASES[raw_provider_id]
                if raw_provider_id in _PROVIDER_ALIASES
                else raw_provider_id
            )
            if provider_id and provider_id not in out:
                out.append(provider_id)
        return out or ["auto"]

    def _unsupported_status(self, provider_id: str) -> MetaSearchProviderStatus:
        return MetaSearchProviderStatus(
            ok=False,
            error=f"unsupported search provider: {provider_id}",
            billing_resource_name=f"search:{provider_id}",
        )

    def _availability_scope(self, company: Company | None) -> str:
        if company is None or not company.company_id.strip():
            return "platform"
        return f"company_{company.company_id.strip()}"
