"""
Пост-retrieval реранк: HTTP-клиент и применение после vector retrieve.

Единая реализация для RAG API, CRM, worker и любых вызывающих из core/apps.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING
from typing import cast as type_cast

import httpx
import tiktoken

from core.ai.providers import PROVIDER_LITSERVE
from core.ai.resolver import (
    COST_ORIGIN_COMPANY,
    COST_ORIGIN_PLATFORM,
    CostOrigin,
    resolve_rerank_for_company,
)
from core.billing import get_billing_service
from core.config.base import BaseSettings
from core.config.llm_openai_compat import (
    resolve_provider_api_key_for_openai_compatible_calls,
    resolve_provider_openai_v1_base_url,
)
from core.context import get_context
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.rag.models import RAGSearchResult
from core.rag.openai_http_contracts import provider_litserve_rerank_http_url
from core.rag_indexing_schema import IndexProfileSearchDefaults
from core.types import JsonValue, require_json_object, require_json_value

if TYPE_CHECKING:
    from core.billing.service import BillingService

logger = get_logger(__name__)


class RerankerClientError(Exception):
    """Ошибка вызова реранкера; ``status_code`` — 422 или 503 для HTTP API."""

    def __init__(self, status_code: int, detail: JsonValue) -> None:
        if status_code not in (422, 503):
            raise ValueError("RerankerClientError допускает только status_code 422 или 503")
        self.status_code: int = status_code
        self.detail: JsonValue = detail
        super().__init__(str(detail))


def _response_body_as_detail(response: httpx.Response) -> JsonValue:
    try:
        return require_json_value(type_cast(JsonValue, response.json()), "reranker error response")
    except Exception:
        text = response.text
        return {"message": text[:8000] if text else ""}


class RerankerHTTPClient:
    """Асинхронный клиент к сервису реранкера."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        cost_per_1m_tokens: float = 5.0,
        platform_markup: float = 1.1,
        billing_resource_id: str = "rerank",
        billing_service: BillingService | None = None,
        cost_origin: CostOrigin = COST_ORIGIN_PLATFORM,
        model: str | None = None,
        api_key: str | None = None,
        extra_request_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout_seconds: float = timeout_seconds
        self.cost_per_1m_tokens: float = cost_per_1m_tokens
        self.platform_markup: float = platform_markup
        self.billing_resource_id: str = billing_resource_id
        self.billing_service: BillingService | None = billing_service
        self.cost_origin: CostOrigin = cost_origin
        self.model: str | None = model.strip() if model is not None and model.strip() else None
        self.api_key: str | None = api_key
        self.extra_request_headers: dict[str, str] | None = dict(extra_request_headers or {}) or None
        self._tokenizer: tiktoken.Encoding = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, query: str, passages: list[str]) -> int:
        total = len(self._tokenizer.encode(query))
        for text in passages:
            total += len(self._tokenizer.encode(text))
        return total

    def calculate_cost(self, token_count: int) -> float:
        base_cost = (token_count / 1_000_000) * self.cost_per_1m_tokens
        return base_cost * self.platform_markup

    def _get_billing_service(self) -> "BillingService":
        if self.billing_service:
            return self.billing_service

        return get_billing_service()

    async def _record_usage(self, token_count: int, cost: float) -> None:
        context = get_context()
        if not context or not context.user or not context.active_company:
            logger.debug("Rerank: нет user/active_company в контексте, биллинг не пишем")
            return

        billing = self.billing_service or self._get_billing_service()
        resource = self.billing_resource_id.strip() or "rerank"
        is_company = self.cost_origin == COST_ORIGIN_COMPANY
        effective_cost = 0.0 if is_company else cost
        resource_name = "rerank:byok" if is_company else f"rerank:{resource}"
        logger.info(
            "Rerank billing: tokens=%s cost=%.4f RUB resource=%s cost_origin=%s",
            token_count,
            effective_cost,
            resource_name,
            self.cost_origin,
        )
        _ = await billing.record_usage(
            user=context.user,
            company=context.active_company,
            resource_name=resource_name,
            cost=effective_cost,
            usage_type=UsageType.RERANK_REQUEST,
            quantity=token_count,
            metadata={
                "model": resource,
                "tokens": token_count,
                "cost_per_1m_tokens": self.cost_per_1m_tokens,
                "platform_markup": self.platform_markup,
                "cost_origin": self.cost_origin,
            },
            cost_origin=self.cost_origin,
        )

    async def rerank(
        self,
        endpoint_url: str,
        query: str,
        results: list[RAGSearchResult],
        *,
        max_candidates: int | None = None,
    ) -> list[RAGSearchResult]:
        if not results:
            return []
        if not endpoint_url or not endpoint_url.strip():
            raise RerankerClientError(
                status_code=422,
                detail="rerank: пустой URL сервиса реранкера",
            )

        pool = list(results)
        if max_candidates is not None:
            pool = pool[:max_candidates]

        passages = [r.content for r in pool]
        token_count = self.count_tokens(query, passages)

        payload = {"query": query, "passages": passages}
        if self.model is not None:
            payload["model"] = self.model

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if self.extra_request_headers:
            headers.update(self.extra_request_headers)

        try:
            async with get_httpx_client(
                timeout=self._timeout_seconds,
                strategy=ProxyStrategy.DIRECT_ONLY,
            ) as client:
                response = await client.post(
                    endpoint_url.strip(),
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as e:
            raise RerankerClientError(
                status_code=503,
                detail={"reason": "timeout", "message": str(e)},
            ) from e
        except httpx.RequestError as e:
            raise RerankerClientError(
                status_code=503,
                detail={"reason": "request_error", "message": str(e)},
            ) from e

        if response.status_code == 503:
            raise RerankerClientError(
                status_code=503,
                detail=_response_body_as_detail(response),
            )
        if response.status_code == 422:
            raise RerankerClientError(
                status_code=422,
                detail=_response_body_as_detail(response),
            )
        if response.status_code != 200:
            detail = _response_body_as_detail(response)
            if response.status_code >= 500:
                raise RerankerClientError(status_code=503, detail=detail)
            raise RerankerClientError(status_code=422, detail=detail)

        data = require_json_object(type_cast(JsonValue, response.json()), "reranker response")
        if "scores" not in data:
            raise RerankerClientError(
                status_code=422,
                detail="Ответ реранкера: ожидается JSON-объект с ключом scores",
            )
        scores_raw = data["scores"]
        if not isinstance(scores_raw, list):
            raise RerankerClientError(
                status_code=422,
                detail="Ответ реранкера: scores должен быть массивом",
            )
        scores: list[float] = []
        for s in scores_raw:
            if isinstance(s, bool) or not isinstance(s, (int, float)):
                raise RerankerClientError(
                    status_code=422,
                    detail="Ответ реранкера: каждый score должен быть числом",
                )
            scores.append(float(s))

        if len(scores) != len(pool):
            raise RerankerClientError(
                status_code=422,
                detail={
                    "reason": "scores_length_mismatch",
                    "expected": len(pool),
                    "got": len(scores),
                },
            )

        cost = self.calculate_cost(token_count)
        await self._record_usage(token_count, cost)

        paired = sorted(zip(scores, pool), key=lambda x: x[0], reverse=True)
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


@dataclass(frozen=True)
class RerankResolution:
    """Итог резолва rerank: enabled/url/cost_origin/api_key/headers."""

    enabled: bool
    provider: str | None
    model: str | None
    url: str | None
    max_candidates: int | None
    cost_origin: CostOrigin
    api_key: str | None = None
    extra_request_headers: dict[str, str] | None = None


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

    rr = settings.rag.reranker
    if rr.provider == "none" and request_rerank is None and prof is None:
        enabled = False

    url: str | None = None
    if prof is not None and prof.url and (u := prof.url.strip()):
        url = u
    if url is None:
        if rr.base_url and (u := rr.base_url.strip()):
            url = u
        elif rr.provider == "provider_litserve":
            url = provider_litserve_rerank_http_url(
                settings.provider_litserve.resolve_openai_v1_base_url()
            )
        elif rr.provider != "none":
            provider_base_url = resolve_provider_openai_v1_base_url(settings.llm, rr.provider)
            url = f"{provider_base_url.rstrip('/')}/rerank"

    max_candidates = prof.max_candidates if prof is not None else None

    company_resolved = resolve_rerank_for_company()
    if company_resolved is not None:
        if not company_resolved.enabled:
            return RerankResolution(
                enabled=False,
                provider=company_resolved.provider,
                model=company_resolved.model,
                url=None,
                max_candidates=max_candidates,
                cost_origin=company_resolved.cost_origin,
            )
        if company_resolved.url:
            return RerankResolution(
                enabled=True,
                provider=company_resolved.provider,
                model=company_resolved.model,
                url=company_resolved.url,
                max_candidates=max_candidates,
                cost_origin=company_resolved.cost_origin,
                api_key=company_resolved.api_key,
                extra_request_headers=company_resolved.extra_request_headers,
            )
        provider = company_resolved.provider
        if provider == PROVIDER_LITSERVE:
            resolved_url = provider_litserve_rerank_http_url(
                settings.provider_litserve.resolve_openai_v1_base_url()
            )
            api_key = company_resolved.api_key
        elif provider:
            provider_base_url = resolve_provider_openai_v1_base_url(settings.llm, provider)
            resolved_url = f"{provider_base_url.rstrip('/')}/rerank"
            provider_api_key = resolve_provider_api_key_for_openai_compatible_calls(
                settings.llm,
                provider,
            )
            api_key = company_resolved.api_key or provider_api_key
        else:
            resolved_url = None
            api_key = company_resolved.api_key
        return RerankResolution(
            enabled=True,
            provider=provider,
            model=company_resolved.model,
            url=resolved_url,
            max_candidates=max_candidates,
            cost_origin=company_resolved.cost_origin,
            api_key=api_key,
            extra_request_headers=company_resolved.extra_request_headers,
        )

    default_api_key = (
        None
        if rr.provider in ("none", PROVIDER_LITSERVE)
        else resolve_provider_api_key_for_openai_compatible_calls(settings.llm, rr.provider)
    )
    default_model = (
        None
        if rr.provider == PROVIDER_LITSERVE and rr.billing_model_id == "rerank"
        else rr.billing_model_id
    )
    return RerankResolution(
        enabled=enabled,
        provider=rr.provider,
        model=default_model,
        url=url,
        max_candidates=max_candidates,
        cost_origin=COST_ORIGIN_PLATFORM,
        api_key=default_api_key,
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
        cost_origin=resolution.cost_origin,
        model=resolution.model,
        api_key=resolution.api_key,
        extra_request_headers=resolution.extra_request_headers,
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


__all__ = [
    "RerankerClientError",
    "RerankerHTTPClient",
    "apply_rerank_after_retrieve",
    "apply_rerank_after_retrieve_grouped",
    "rerank_options",
]
