"""HTTP client for provider_litserve KeyBERT endpoint."""

from __future__ import annotations

from typing import cast

import httpx

from core.http import ProxyStrategy, get_httpx_client
from core.logging import get_logger
from core.types import JsonValue, require_json_object, require_json_value

logger = get_logger(__name__)


class AIKeybertClientError(Exception):
    def __init__(self, status_code: int, detail: JsonValue) -> None:
        self.status_code: int = status_code
        self.detail: JsonValue = detail
        super().__init__(str(detail))


def _response_body_as_detail(response: httpx.Response) -> JsonValue:
    try:
        return require_json_value(cast(JsonValue, response.json()), "keybert error response")
    except Exception:
        text = response.text
        return {"message": text[:8000] if text else ""}


class AIKeybertHTTPClient:
    def __init__(
        self,
        *,
        timeout_seconds: float = 120.0,
        model: str | None = None,
        api_key: str | None = None,
        extra_request_headers: dict[str, str] | None = None,
    ) -> None:
        self._timeout_seconds: float = timeout_seconds
        self.model: str | None = model.strip() if model is not None and model.strip() else None
        self.api_key: str | None = api_key
        self.extra_request_headers: dict[str, str] | None = dict(extra_request_headers or {}) or None

    async def extract_keywords(
        self,
        endpoint_url: str,
        text: str,
        *,
        top_n: int,
        use_mmr: bool = True,
        diversity: float = 0.7,
        model: str | None = None,
    ) -> list[tuple[str, float]]:
        if not text.strip():
            return []
        if not endpoint_url.strip():
            raise AIKeybertClientError(
                status_code=422,
                detail="keybert: empty service URL",
            )

        payload: dict[str, JsonValue] = {
            "text": text,
            "top_n": top_n,
            "keyphrase_ngram_range": [1, 3],
            "use_mmr": use_mmr,
            "diversity": diversity,
        }
        if self.model is not None:
            payload["model"] = self.model
        elif model is not None and model.strip():
            payload["model"] = model.strip()

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
        except httpx.TimeoutException as exc:
            raise AIKeybertClientError(
                status_code=503,
                detail={"reason": "timeout", "message": str(exc)},
            ) from exc
        except httpx.RequestError as exc:
            raise AIKeybertClientError(
                status_code=503,
                detail={"reason": "request_error", "message": str(exc)},
            ) from exc

        if response.status_code != 200:
            raise AIKeybertClientError(
                status_code=response.status_code,
                detail=_response_body_as_detail(response),
            )

        body = require_json_object(
            require_json_value(cast(JsonValue, response.json()), "keybert response"),
            "keybert response",
        )
        keywords_raw = body.get("keywords")
        if not isinstance(keywords_raw, list):
            raise AIKeybertClientError(
                status_code=503,
                detail={"reason": "invalid_response", "field": "keywords"},
            )

        out: list[tuple[str, float]] = []
        for item in keywords_raw:
            if not isinstance(item, dict):
                continue
            term_raw = item.get("term")
            score_raw = item.get("score")
            if not isinstance(term_raw, str) or not term_raw.strip():
                continue
            score = float(score_raw) if isinstance(score_raw, (int, float)) else 0.0
            out.append((term_raw.strip(), score))
        return out
