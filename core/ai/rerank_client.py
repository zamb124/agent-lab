from __future__ import annotations

from typing import cast as type_cast

import httpx
import tiktoken

import core.tracing.attributes as trace_attributes
from core.ai.models import AICostOrigin
from core.context import get_context
from core.http import ProxyStrategy, get_httpx_client
from core.models.billing_models import UsageType
from core.tracing.operation_span import traced_operation
from core.types import JsonValue, require_json_object, require_json_value


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
        billing_resource_id: str = "rerank",
        cost_origin: AICostOrigin = "platform",
        model: str | None = None,
        api_key: str | None = None,
        extra_request_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout_seconds: float = timeout_seconds
        self.billing_resource_id: str = billing_resource_id
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

    async def _record_usage_span(self, token_count: int) -> None:
        """Billing span `rerank.{model}`: quantity — токены; цена — `billing.resource_base_prices.rerank`."""
        context = get_context()
        if context is None or context.active_company is None:
            raise ValueError('Rerank: Context with active_company is required for billing')
        resource = self.billing_resource_id.strip() or "rerank"
        is_company = self.cost_origin == "company"
        resource_name = "rerank:byok" if is_company else f"rerank:{resource}"
        async with traced_operation(
            f"rerank.{resource}",
            event_type="rag.rerank",
            operation_category="rag",
            billing_usage_type=UsageType.RERANK_REQUEST.value,
            billing_resource_name=resource_name,
            billing_quantity=token_count,
            billing_pending_settlement=True,
            billing_cost_origin=self.cost_origin,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: context.active_company.company_id,
                trace_attributes.ATTR_USER_ID: context.user.user_id,
                "platform.rerank.model": resource,
                "platform.rerank.tokens": token_count,
            },
        ):
            pass

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

        await self._record_usage_span(token_count)
        return scores


__all__ = ["AIRerankerClientError", "AIRerankerHTTPClient"]
