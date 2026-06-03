from __future__ import annotations

from typing import TYPE_CHECKING
from typing import cast as type_cast

import httpx
import tiktoken

from core.ai.models import AICostOrigin
from core.billing import get_billing_service
from core.context import get_context
from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.types import JsonValue, require_json_object, require_json_value

if TYPE_CHECKING:
    from core.billing.service import BillingService

logger = get_logger(__name__)


class AIRerankerClientError(Exception):
    def __init__(self, status_code: int, detail: JsonValue) -> None:
        if status_code not in (422, 503):
            raise ValueError("AIRerankerClientError allows only status_code 422 or 503")
        self.status_code: int = status_code
        self.detail: JsonValue = detail
        super().__init__(str(detail))


def _response_body_as_detail(response: httpx.Response) -> JsonValue:
    try:
        return require_json_value(type_cast(JsonValue, response.json()), "reranker error response")
    except Exception:
        text = response.text
        return {"message": text[:8000] if text else ""}


class AIRerankerHTTPClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 60.0,
        cost_per_1m_tokens: float = 5.0,
        platform_markup: float = 1.1,
        billing_resource_id: str = "rerank",
        billing_service: "BillingService | None" = None,
        cost_origin: AICostOrigin = "platform",
        model: str | None = None,
        api_key: str | None = None,
        extra_request_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout_seconds: float = timeout_seconds
        self.cost_per_1m_tokens: float = cost_per_1m_tokens
        self.platform_markup: float = platform_markup
        self.billing_resource_id: str = billing_resource_id
        self.billing_service: BillingService | None = billing_service
        self.cost_origin: AICostOrigin = cost_origin
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
            logger.debug("Rerank: no user/active_company context, billing is skipped")
            return

        billing = self.billing_service or self._get_billing_service()
        resource = self.billing_resource_id.strip() or "rerank"
        is_company = self.cost_origin == "company"
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

    async def rerank_scores(
        self,
        endpoint_url: str,
        query: str,
        passages: list[str],
    ) -> list[float]:
        if not passages:
            return []
        if not endpoint_url or not endpoint_url.strip():
            raise AIRerankerClientError(
                status_code=422,
                detail="rerank: empty reranker service URL",
            )

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
            raise AIRerankerClientError(
                status_code=503,
                detail={"reason": "timeout", "message": str(e)},
            ) from e
        except httpx.RequestError as e:
            raise AIRerankerClientError(
                status_code=503,
                detail={"reason": "request_error", "message": str(e)},
            ) from e

        if response.status_code == 503:
            raise AIRerankerClientError(
                status_code=503,
                detail=_response_body_as_detail(response),
            )
        if response.status_code == 422:
            raise AIRerankerClientError(
                status_code=422,
                detail=_response_body_as_detail(response),
            )
        if response.status_code != 200:
            detail = _response_body_as_detail(response)
            if response.status_code >= 500:
                raise AIRerankerClientError(status_code=503, detail=detail)
            raise AIRerankerClientError(status_code=422, detail=detail)

        data = require_json_object(type_cast(JsonValue, response.json()), "reranker response")
        if "scores" not in data:
            raise AIRerankerClientError(
                status_code=422,
                detail="Reranker response must be a JSON object with key scores",
            )
        scores_raw = data["scores"]
        if not isinstance(scores_raw, list):
            raise AIRerankerClientError(
                status_code=422,
                detail="Reranker response scores must be an array",
            )
        scores: list[float] = []
        for score in scores_raw:
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                raise AIRerankerClientError(
                    status_code=422,
                    detail="Every reranker score must be a number",
                )
            scores.append(float(score))

        if len(scores) != len(passages):
            raise AIRerankerClientError(
                status_code=422,
                detail={
                    "reason": "scores_length_mismatch",
                    "expected": len(passages),
                    "got": len(scores),
                },
            )

        cost = self.calculate_cost(token_count)
        await self._record_usage(token_count, cost)
        return scores


__all__ = ["AIRerankerClientError", "AIRerankerHTTPClient"]
