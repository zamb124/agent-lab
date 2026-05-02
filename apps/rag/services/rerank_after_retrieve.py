"""HTTP-реранг после retrieve для REST search."""

from __future__ import annotations

from collections import defaultdict

from core.config.base import BaseSettings
from core.rag.openai_http_contracts import provider_litserve_rerank_http_url
from core.rag_indexing_schema import IndexProfileSearchDefaults
from core.rag.models import RAGSearchResult
from .reranker_client import RerankerClientError, RerankerHTTPClient


def _rerank_options(
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
) -> tuple[bool, str | None, int | None]:
    effective_sd = profile_sd
    if effective_sd is None:
        effective_sd = settings.rag.document_indexing.search_defaults

    prof = effective_sd.reranker if effective_sd is not None else None
    if request_rerank is not None:
        enabled = request_rerank
    elif prof is not None:
        enabled = prof.enabled
    else:
        enabled = True

    url: str | None = None
    if prof is not None and prof.url and (u := prof.url.strip()):
        url = u
    if url is None:
        rr = settings.rag.reranker
        if rr.base_url and (u := rr.base_url.strip()):
            url = u
        elif rr.provider == "provider_litserve":
            url = provider_litserve_rerank_http_url(
                settings.provider_litserve.resolve_openai_v1_base_url()
            )

    max_candidates = prof.max_candidates if prof is not None else None
    return enabled, url, max_candidates


async def apply_rerank_after_retrieve(
    *,
    results: list[RAGSearchResult],
    query: str,
    provider_name: str,
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
) -> list[RAGSearchResult]:
    enabled, url, max_candidates = _rerank_options(request_rerank, profile_sd, settings)
    if not enabled:
        return results
    if provider_name != "pgvector":
        raise RerankerClientError(
            status_code=422,
            detail="rerank поддерживается только для провайдера pgvector",
        )
    if not url:
        raise RerankerClientError(
            status_code=422,
            detail="rerank включён, но URL реранкера не задан (профиль или rag.reranker.base_url)",
        )
    rr = settings.rag.reranker
    client = RerankerHTTPClient(
        timeout_seconds=rr.timeout_seconds,
        cost_per_1m_tokens=rr.cost_per_1m_tokens,
        platform_markup=rr.platform_markup,
        billing_resource_id=rr.billing_model_id,
    )
    return await client.rerank(url, query, results, max_candidates=max_candidates)


async def apply_rerank_after_retrieve_grouped(
    *,
    results_by_namespace: dict[str, list[RAGSearchResult]],
    namespace_order: list[str],
    query: str,
    provider_name: str,
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
) -> dict[str, list[RAGSearchResult]]:
    empty = {ns: list(results_by_namespace.get(ns, [])) for ns in namespace_order}
    flat = [r for ns in namespace_order for r in results_by_namespace.get(ns, [])]
    if not flat:
        return empty

    reranked = await apply_rerank_after_retrieve(
        results=flat,
        query=query,
        provider_name=provider_name,
        request_rerank=request_rerank,
        profile_sd=profile_sd,
        settings=settings,
    )
    by_ns: dict[str, list[RAGSearchResult]] = defaultdict(list)
    for item in reranked:
        by_ns[item.namespace].append(item)
    for bucket in by_ns.values():
        bucket.sort(key=lambda r: r.score, reverse=True)
    return {ns: by_ns.get(ns, []) for ns in namespace_order}
