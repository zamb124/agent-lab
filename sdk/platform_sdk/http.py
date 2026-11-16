"""HTTP-клиент CLI: envelope ошибок, повторы безопасных запросов, SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping

import httpx
from pydantic import ValidationError

from platform_sdk.context_store import PlatformContext
from platform_sdk.errors import (
    EXIT_UNAVAILABLE,
    PlatformCliError,
    error_from_envelope,
    retryable_status,
)
from platform_sdk.json_types import JsonObject, JsonValue, as_json, require_object


class PlatformClient:
    def __init__(
        self,
        context: PlatformContext,
        *,
        timeout: float,
        namespace: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        self.context = context
        self.namespace = namespace
        self._timeout = timeout
        self._owns_client = http is None
        headers = {
            "Authorization": f"Bearer {context.api_key}",
            "Accept": "application/json",
        }
        if namespace is not None and namespace != "":
            headers["X-Platform-Namespace"] = namespace
        self._http = (
            http
            if http is not None
            else httpx.AsyncClient(
                base_url=context.host,
                timeout=timeout,
                headers=headers,
            )
        )
        self._extra_headers = headers if http is not None else {}

    async def close(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        json_body: object | None = None,
        params: Mapping[str, str | int] | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool = False,
    ) -> JsonValue:
        response = await self._send(
            method,
            path,
            json_body=None if json_body is None else as_json(json_body, path),
            params=params,
            content=content,
            headers=headers,
            retry=retry,
        )
        if response.status_code == 204 or response.content == b"":
            return None
        return self._decode(response)

    async def request_bytes(self, method: str, path: str) -> tuple[JsonObject, bytes]:
        response = await self._send(method, path, retry=True)
        header_name = response.headers.get("content-disposition", "")
        return {
            "content_disposition": header_name,
            "content_type": response.headers.get("content-type", ""),
        }, response.content

    async def stream(
        self,
        method: str,
        path: str,
        *,
        json_body: object,
        headers: Mapping[str, str] | None = None,
    ) -> AsyncIterator[JsonObject]:
        body = require_object(as_json(json_body, path), path)
        request_headers = dict(self._extra_headers)
        if headers is not None:
            request_headers.update(headers)
        try:
            async with self._http.stream(
                method,
                path,
                json=body,
                headers=request_headers,
                timeout=self._timeout,
            ) as response:
                if response.status_code >= 400:
                    raw = await response.aread()
                    self._raise_http(response.status_code, raw)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "" or payload == "[DONE]":
                        continue
                    parsed = json.loads(payload)
                    yield require_object(as_json(parsed, "sse"), "sse")
        except httpx.HTTPError as exc:
            raise PlatformCliError(
                error_code="unavailable",
                error_detail=str(exc),
                exit_code=EXIT_UNAVAILABLE,
                retryable=True,
            ) from exc

    async def _send(
        self,
        method: str,
        path: str,
        *,
        json_body: JsonValue | None = None,
        params: Mapping[str, str | int] | None = None,
        content: bytes | None = None,
        headers: Mapping[str, str] | None = None,
        retry: bool = False,
    ) -> httpx.Response:
        request_headers = dict(self._extra_headers)
        if headers is not None:
            request_headers.update(headers)
        attempts = 4 if retry else 1
        last_error: PlatformCliError | None = None
        for attempt in range(attempts):
            try:
                response = await self._http.request(
                    method,
                    path,
                    json=json_body,
                    params=params,
                    content=content,
                    headers=request_headers,
                    timeout=self._timeout,
                )
            except httpx.HTTPError as exc:
                last_error = PlatformCliError(
                    error_code="unavailable",
                    error_detail=str(exc),
                    exit_code=EXIT_UNAVAILABLE,
                    retryable=True,
                )
                if attempt + 1 == attempts:
                    raise last_error from exc
                await asyncio.sleep(0.4 * (2**attempt))
                continue
            if response.status_code < 400:
                return response
            if retry and retryable_status(response.status_code) and attempt + 1 < attempts:
                await asyncio.sleep(0.4 * (2**attempt))
                continue
            self._raise_http(response.status_code, response.content)
        if last_error is not None:
            raise last_error
        raise PlatformCliError(
            error_code="internal",
            error_detail="request finished without a response",
            exit_code=1,
        )

    def _decode(self, response: httpx.Response) -> JsonValue:
        try:
            parsed = response.json()
        except json.JSONDecodeError as exc:
            raise PlatformCliError(
                error_code="ws_invalid_payload",
                error_detail=f"Response is not JSON: {exc}",
                exit_code=3,
                http_status=response.status_code,
            ) from exc
        return as_json(parsed, response.request.url.path)

    def _raise_http(self, status: int, raw: bytes) -> None:
        text = raw.decode("utf-8", errors="replace") if raw else ""
        try:
            loaded: object = json.loads(text) if text else {}
        except json.JSONDecodeError:
            loaded = {"error_detail": text}
        try:
            raise error_from_envelope(status, loaded)
        except ValidationError:
            raise error_from_envelope(status, {"error_detail": text or f"HTTP {status}"}) from None
