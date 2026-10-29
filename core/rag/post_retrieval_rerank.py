"""
Пост-retrieval реранк: HTTP-клиент и применение после vector retrieve.

Единая реализация для RAG API, CRM, worker и любых вызывающих из core/apps.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from dataclasses import dataclass

import core.tracing.attributes as trace_attributes
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
from core.cache.ttl_model_cache import RedisTextCache
from core.config.base import BaseSettings
from core.rag.models import RAGSearchResult
from core.rag_indexing_schema import IndexProfileSearchDefaults
from core.tracing.operation_span import traced_operation


class RerankScoreCache:
    """
    Redis-кэш rerank-скорингов по ``(model, query_hash, chunk_id)``.

    Кросс-энкодер детерминирован для пары (query, passage), поэтому скор
    можно переиспользовать между повторными запросами (пагинация SERP,
    повторные поиски) без нового GPU-вызова.
    """

    def __init__(
        self,
        redis_text_cache: RedisTextCache,
        *,
        ttl_seconds: int = 1800,
        key_prefix: str = "rag:rerank_score",
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("RerankScoreCache: ttl_seconds must be positive")
        self._redis: RedisTextCache = redis_text_cache
        self._ttl_seconds: int = ttl_seconds
        self._key_prefix: str = key_prefix

    def _key(self, *, model: str, query: str, chunk_id: str) -> str:
        query_hash = hashlib.sha256(f"{model}\n{query}".encode("utf-8")).hexdigest()[:32]
        return f"{self._key_prefix}:{query_hash}:{chunk_id}"

    async def get_scores(
        self,
        *,
        model: str,
        query: str,
        chunk_ids: list[str],
    ) -> dict[str, float]:
        raw_values = await asyncio.gather(
            *(self._redis.get(self._key(model=model, query=query, chunk_id=chunk_id)) for chunk_id in chunk_ids)
        )
        cached: dict[str, float] = {}
        for chunk_id, raw_value in zip(chunk_ids, raw_values):
            if raw_value is None:
                continue
            # Кэш — внешняя граница: испорченное значение просто пере-скорится.
            try:
                cached[chunk_id] = float(raw_value)
            except ValueError:
                continue
        return cached

    async def set_scores(
        self,
        *,
        model: str,
        query: str,
        scores_by_chunk_id: dict[str, float],
    ) -> None:
        _ = await asyncio.gather(
            *(
                self._redis.set(
                    self._key(model=model, query=query, chunk_id=chunk_id),
                    repr(score),
                    ttl=self._ttl_seconds,
                )
                for chunk_id, score in scores_by_chunk_id.items()
            )
        )


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
        raise ValueError('ResolvedAIModel[rerank].metadata.enabled must be bool')
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


async def apply_rerank_after_retrieve_by_score_desc(
    *,
    results: list[RAGSearchResult],
    query: str,
    provider_name: str,
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
    request_rerank_max_candidates: int | None = None,
    score_cache: RerankScoreCache | None = None,
) -> list[RAGSearchResult]:
    resolution = rerank_options(request_rerank, profile_sd, settings)
    enabled = resolution.enabled
    url = resolution.url
    max_candidates = request_rerank_max_candidates
    if max_candidates is None:
        max_candidates = resolution.max_candidates
    if not enabled:
        return results
    if provider_name != "pgvector":
        raise AIRerankerClientError(
            status_code=422,
            detail='rerank is supported only for the pgvector provider',
        )
    if not url:
        raise AIRerankerClientError(
            status_code=422,
            detail='rerank is enabled but reranker URL is not set (profile or rag.reranker.base_url)',
        )
    pool = list(results)
    if max_candidates is not None:
        pool = pool[:max_candidates]
    async with traced_operation(
        "rag.rerank.after_retrieve",
        event_type="rag.rerank",
        operation_category="rag_rerank",
        extra_attributes={
            trace_attributes.ATTR_RAG_STAGE: "rerank",
            "platform.rag.rerank_pool_size": len(pool),
        },
    ):
        scores = await _rerank_pool_scores(
            pool=pool,
            query=query,
            url=url,
            resolution=resolution,
            settings=settings,
            score_cache=score_cache,
        )
        adjusted: list[tuple[float, float, RAGSearchResult]] = []
        for rerank_score, item in zip(scores, pool):
            freshness_multiplier = item.provenance.get("freshness_multiplier")
            final_score = rerank_score
            if isinstance(freshness_multiplier, (int, float)) and not isinstance(freshness_multiplier, bool):
                final_score = rerank_score * float(freshness_multiplier)
            adjusted.append((final_score, rerank_score, item))
        adjusted.sort(key=lambda entry: entry[0], reverse=True)
        out: list[RAGSearchResult] = []
        for final_score, rerank_score, item in adjusted:
            prov = dict(item.provenance)
            prov["rerank"] = True
            prov["rerank_score"] = rerank_score
            out.append(
                item.model_copy(
                    update={
                        "score": final_score,
                        "provenance": prov,
                    }
                )
            )
        return out


async def _rerank_pool_scores(
    *,
    pool: list[RAGSearchResult],
    query: str,
    url: str,
    resolution: RerankResolution,
    settings: BaseSettings,
    score_cache: RerankScoreCache | None,
) -> list[float]:
    """
    Скор для каждого элемента pool: сперва Redis-кэш по chunk_id,
    затем один batch-вызов реранкера только для непокрытых чанков.
    """
    rr = settings.rag.reranker
    cache_model = resolution.model or resolution.billing_resource_id or rr.billing_model_id
    # Кэшируются только чанки со стабильным chunk_id; элементы без него
    # (не-pgvector источники) всегда скорятся заново.
    chunk_ids: list[str | None] = [item.chunk_id for item in pool]
    cacheable_chunk_ids = [chunk_id for chunk_id in chunk_ids if chunk_id is not None]
    cached_scores: dict[str, float] = {}
    if score_cache is not None and cacheable_chunk_ids:
        cached_scores = await score_cache.get_scores(
            model=cache_model, query=query, chunk_ids=cacheable_chunk_ids
        )
    missing_indexes = [
        index
        for index, chunk_id in enumerate(chunk_ids)
        if chunk_id is None or chunk_id not in cached_scores
    ]
    fresh_scores_by_index: dict[int, float] = {}
    if missing_indexes:
        passages = [pool[index].content for index in missing_indexes]
        fresh_scores = await rerank_scores(
            endpoint_url=url,
            query=query,
            passages=passages,
            timeout_seconds=rr.timeout_seconds,
            billing_resource_id=resolution.billing_resource_id or resolution.model or rr.billing_model_id,
            cost_origin=_runtime_cost_origin(resolution.cost_origin),
            model=resolution.model,
            api_key=resolution.api_key,
            extra_request_headers=resolution.extra_request_headers,
        )
        fresh_scores_by_index = dict(zip(missing_indexes, fresh_scores))
        if score_cache is not None:
            fresh_scores_by_chunk_id: dict[str, float] = {}
            for index, score in fresh_scores_by_index.items():
                fresh_chunk_id = chunk_ids[index]
                if fresh_chunk_id is not None:
                    fresh_scores_by_chunk_id[fresh_chunk_id] = score
            if fresh_scores_by_chunk_id:
                await score_cache.set_scores(
                    model=cache_model,
                    query=query,
                    scores_by_chunk_id=fresh_scores_by_chunk_id,
                )
    ordered_scores: list[float] = []
    for index, chunk_id in enumerate(chunk_ids):
        if index in fresh_scores_by_index:
            ordered_scores.append(fresh_scores_by_index[index])
        else:
            if chunk_id is None:
                raise RuntimeError('rerank pool scoring: item without chunk_id is not covered by batch scoring')
            ordered_scores.append(cached_scores[chunk_id])
    return ordered_scores


async def apply_rerank_after_retrieve_grouped_by_score_desc(
    *,
    results_by_namespace: dict[str, list[RAGSearchResult]],
    namespace_order: list[str],
    query: str,
    provider_name: str,
    request_rerank: bool | None,
    profile_sd: IndexProfileSearchDefaults | None,
    settings: BaseSettings,
    request_rerank_max_candidates: int | None = None,
    score_cache: RerankScoreCache | None = None,
) -> dict[str, list[RAGSearchResult]]:
    empty = {ns: list(results_by_namespace.get(ns, [])) for ns in namespace_order}
    flat = [r for ns in namespace_order for r in results_by_namespace.get(ns, [])]
    if not flat:
        return empty

    reranked = await apply_rerank_after_retrieve_by_score_desc(
        results=flat,
        query=query,
        provider_name=provider_name,
        request_rerank=request_rerank,
        profile_sd=profile_sd,
        settings=settings,
        request_rerank_max_candidates=request_rerank_max_candidates,
        score_cache=score_cache,
    )
    by_ns: dict[str, list[RAGSearchResult]] = defaultdict(list)
    for item in reranked:
        by_ns[item.namespace].append(item)
    for bucket in by_ns.values():
        bucket.sort(key=lambda r: r.score, reverse=True)
    return {ns: by_ns.get(ns, []) for ns in namespace_order}


__all__ = [
    "apply_rerank_after_retrieve_by_score_desc",
    "apply_rerank_after_retrieve_grouped_by_score_desc",
    "rerank_options",
]
