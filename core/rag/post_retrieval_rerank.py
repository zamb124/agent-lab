"""
Пост-retrieval реранк: HTTP-клиент и применение после vector retrieve.

Единая реализация для RAG API, CRM, worker и любых вызывающих из core/apps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from core.ai.models import AICostOrigin, ResolvedAIModel
from core.ai.providers import AICapability
from core.ai.rerank_client import AIRerankerClientError
from core.ai.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    CostOrigin,
    resolve_ai_model,
)
from core.ai.runtime import rerank_scores
from core.config.base import BaseSettings
from core.rag.models import RAGSearchResult
from core.rag_indexing_schema import IndexProfileSearchDefaults


@dataclass(frozen=True)
class RerankResolution:
    """Итог резолва rerank: enabled/url/cost_origin/api_key/headers."""

    enabled: bool
    provider: str | None
    model: str | None
    url: str | None
    max_candidates: int | None
    cost_origin: CostOrigin
    billing_resource_id: str | None = None
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None


def _ai_cost_origin(resolved: ResolvedAIModel) -> CostOrigin:
    if resolved.cost_origin == "company":
        return COST_ORIGIN_COMPANY
    return COST_ORIGIN_PLATFORM


def _runtime_cost_origin(value: CostOrigin) -> AICostOrigin:
    if value == COST_ORIGIN_COMPANY:
        return "company"
    return "platform"


def _ai_rerank_enabled(resolved: ResolvedAIModel) -> bool:
    raw = resolved.metadata.get("enabled")
    if not isinstance(raw, bool):
        raise ValueError("ResolvedAIModel[rerank].metadata.enabled должен быть bool")
    return raw


def _ai_rerank_billing_resource_id(resolved: ResolvedAIModel) -> str:
    raw = resolved.metadata.get("billing_resource_id")
    if not isinstance(raw, str) or not raw.strip():
        return resolved.model or "rerank"
    return raw.strip()


def rerank_options(
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
) -> RerankResolution:
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

    max_candidates = prof.max_candidates if prof is not None else None

    resolved = resolve_ai_model(
        AICapability.RERANK,
        include_platform_default=True,
    )
    if resolved is None:
        return RerankResolution(
            enabled=False,
            provider=None,
            model=None,
            url=None,
            max_candidates=max_candidates,
            cost_origin=COST_ORIGIN_PLATFORM,
        )
    ai_enabled = _ai_rerank_enabled(resolved)
    effective_enabled = enabled and ai_enabled
    resolved_url = url or resolved.endpoint_url
    return RerankResolution(
        enabled=effective_enabled,
        provider=resolved.provider,
        model=resolved.model,
        url=resolved_url if effective_enabled else None,
        max_candidates=max_candidates,
        cost_origin=_ai_cost_origin(resolved),
        billing_resource_id=_ai_rerank_billing_resource_id(resolved),
        api_key=resolved.api_key,
        extra_request_headers={key: str(value) for key, value in resolved.headers.items()} or None,
    )


async def apply_rerank_after_retrieve(
    *,
    results: list[RAGSearchResult],
    query: str,
    provider_name: str,
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
) -> list[RAGSearchResult]:
    resolution = rerank_options(request_rerank, profile_sd, settings)
    enabled = resolution.enabled
    url = resolution.url
    max_candidates = resolution.max_candidates
    if not enabled:
        return results
    if provider_name != "pgvector":
        raise AIRerankerClientError(
            status_code=422,
            detail="rerank поддерживается только для провайдера pgvector",
        )
    if not url:
        raise AIRerankerClientError(
            status_code=422,
            detail="rerank включён, но URL реранкера не задан (профиль или rag.reranker.base_url)",
        )
    rr = settings.rag.reranker
    pool = list(results)
    if max_candidates is not None:
        pool = pool[:max_candidates]
    passages = [item.content for item in pool]
    scores = await rerank_scores(
        endpoint_url=url,
        query=query,
        passages=passages,
        timeout_seconds=rr.timeout_seconds,
        cost_per_1m_tokens=rr.cost_per_1m_tokens,
        platform_markup=rr.platform_markup,
        billing_resource_id=resolution.billing_resource_id or resolution.model or rr.billing_model_id,
        cost_origin=_runtime_cost_origin(resolution.cost_origin),
        model=resolution.model,
        api_key=resolution.api_key,
        extra_request_headers=resolution.extra_request_headers,
    )
    paired = sorted(zip(scores, pool), key=lambda item: item[0], reverse=True)
    out: list[RAGSearchResult] = []
    for score, item in paired:
        prov = dict(item.provenance)
        prov["rerank"] = True
        prov["rerank_score"] = score
        out.append(
            RAGSearchResult(
                content=item.content,
                score=score,
                document_id=item.document_id,
                document_name=item.document_name,
                metadata=item.metadata,
                namespace=item.namespace,
                chunk_id=item.chunk_id,
                provenance=prov,
            )
        )
    return out


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


__all__ = [
    "apply_rerank_after_retrieve",
    "apply_rerank_after_retrieve_grouped",
    "rerank_options",
]
