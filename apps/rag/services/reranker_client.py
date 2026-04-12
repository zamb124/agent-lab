"""
HTTP-клиент реранкера (OpenAI-совместимый POST на HTTP-gateway RAG и аналоги).

``endpoint_url`` — полный URL эндпоинта (например ``http://host:8014/v1/rerank``), как в ``provider_litserve_rerank_http_url``.

Контракт: POST JSON с полями ``query`` и ``passages`` (тексты чанков в порядке
кандидатов); ответ 200 с полем ``scores`` — числа той же длины, что и ``passages``.
Учёт использования: tiktoken (как у ``EmbeddingService``) и ``BillingService`` при наличии контекста user/company.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Optional

import httpx
import tiktoken

from core.context import get_context
from core.http import get_httpx_client
from core.models.billing_models import UsageType
from core.rag.models import RAGSearchResult

if TYPE_CHECKING:
    from core.billing.service import BillingService

logger = logging.getLogger(__name__)


class RerankerClientError(Exception):
    """Ошибка вызова реранкера; ``status_code`` — 422 или 503 для HTTP API."""

    def __init__(self, status_code: int, detail: Any) -> None:
        if status_code not in (422, 503):
            raise ValueError("RerankerClientError допускает только status_code 422 или 503")
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def _response_body_as_detail(response: httpx.Response) -> Any:
    try:
        return response.json()
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
        billing_service: Optional["BillingService"] = None,
    ) -> None:
        self._timeout_seconds = timeout_seconds
        self.cost_per_1m_tokens = cost_per_1m_tokens
        self.platform_markup = platform_markup
        self.billing_resource_id = billing_resource_id
        self.billing_service = billing_service
        self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, query: str, passages: List[str]) -> int:
        """Число токенов по запросу и пассажам (оценка для биллинга)."""
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
        from core.billing import get_billing_service

        return get_billing_service()

    async def _record_usage(self, token_count: int, cost: float) -> None:
        context = get_context()
        if not context or not context.user or not context.active_company:
            logger.debug("Rerank: нет user/active_company в контексте, биллинг не пишем")
            return

        billing = self.billing_service or self._get_billing_service()
        resource = self.billing_resource_id.strip() or "rerank"
        logger.info(
            "Rerank billing: tokens=%s cost=%.4f RUB resource=rerank:%s",
            token_count,
            cost,
            resource,
        )
        await billing.record_usage(
            user=context.user,
            company=context.active_company,
            resource_name=f"rerank:{resource}",
            cost=cost,
            usage_type=UsageType.RERANK_REQUEST,
            quantity=token_count,
            metadata={
                "model": resource,
                "tokens": token_count,
                "cost_per_1m_tokens": self.cost_per_1m_tokens,
                "platform_markup": self.platform_markup,
            },
        )

    async def rerank(
        self,
        endpoint_url: str,
        query: str,
        results: list[RAGSearchResult],
        *,
        max_candidates: int | None = None,
    ) -> list[RAGSearchResult]:
        """
        Пересортировывает результаты по скорам реранкера.

        Результаты без изменений, если список пуст.
        """
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

        try:
            async with get_httpx_client(
                timeout=self._timeout_seconds,
                proxy=False,
            ) as client:
                response = await client.post(
                    endpoint_url.strip(),
                    json=payload,
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
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

        data = response.json()
        if not isinstance(data, dict) or "scores" not in data:
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
