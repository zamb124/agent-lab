"""
Обогащает JSON-ответы с HTTP status >= 400 полями request_id, trace_id, service и
(для компании system) observability.logs_explore_url.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Protocol, TypeGuard, override

from starlette.background import BackgroundTask
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from core.app_state import get_request_company_id, get_request_correlation_ids
from core.config import get_settings
from core.logging import get_logger
from core.observability.error_payload import try_merge_platform_error_into_dict
from core.types import JsonObject, parse_json_object

_LOGGER = get_logger(__name__)

_MAX_BODY_BYTES = 65536


class BodyIteratorResponse(Protocol):
    body_iterator: AsyncIterator[bytes]
    status_code: int
    headers: MutableHeaders
    media_type: str | None
    background: BackgroundTask | None


def _has_body_iterator(response: Response) -> TypeGuard[BodyIteratorResponse]:
    return hasattr(response, "body_iterator")


class PlatformHttpErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Последний (наружный) middleware в create_service_app — видит финальный Response."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        service_name: str,
    ) -> None:
        super().__init__(app)
        if not service_name.strip():
            raise ValueError("PlatformHttpErrorEnvelopeMiddleware: service_name обязателен")
        self._service_name: str = service_name.strip()

    @override
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        if response.status_code < 400:
            return response

        ct = response.headers.get("content-type", "")
        if "application/json" not in ct:
            return response

        body = b""
        try:
            if not _has_body_iterator(response):
                return response
            async for chunk in response.body_iterator:
                body += chunk
        except Exception:
            _LOGGER.warning(
                "platform_error_envelope.body_read_failed",
                status_code=response.status_code,
            )
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        if not body.strip():
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        try:
            if len(body) > _MAX_BODY_BYTES:
                return Response(
                    content=body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                    background=response.background,
                )
            decoded: JsonObject = parse_json_object(body.decode("utf-8"), "http error response")
        except (UnicodeDecodeError, ValueError):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        correlation = get_request_correlation_ids(request)

        settings = get_settings()
        merged = try_merge_platform_error_into_dict(
            decoded,
            trace_id=correlation.trace_id if correlation is not None else None,
            platform_request_id=correlation.request_id if correlation is not None else None,
            service_name=self._service_name,
            logging_cfg=settings.logging,
            active_company_id=get_request_company_id(request),
        )

        if merged is decoded:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        out = json.dumps(merged, ensure_ascii=False).encode("utf-8")
        hdrs = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(
            content=out,
            status_code=response.status_code,
            headers=hdrs,
            media_type="application/json",
            background=response.background,
        )
