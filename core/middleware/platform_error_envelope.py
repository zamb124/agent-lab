"""
Обогащает JSON-ответы с HTTP status >= 400 полями request_id, trace_id, service и
(для компании system) observability.logs_explore_url.
"""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings
from core.logging import get_logger
from core.observability.error_payload import try_merge_platform_error_into_dict

_LOGGER = get_logger(__name__)

_MAX_BODY_BYTES = 65536


class PlatformHttpErrorEnvelopeMiddleware(BaseHTTPMiddleware):
    """Последний (наружный) middleware в create_service_app — видит финальный Response."""

    def __init__(
        self,
        app,
        *,
        service_name: str,
    ) -> None:
        super().__init__(app)
        if not isinstance(service_name, str) or not service_name.strip():
            raise ValueError("PlatformHttpErrorEnvelopeMiddleware: service_name обязателен")
        self._service_name = service_name.strip()

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        if response.status_code < 400:
            return response

        ct = response.headers.get("content-type", "")
        if "application/json" not in ct:
            return response

        body = b""
        try:
            async for chunk in response.body_iterator:
                body += chunk
        except Exception:
            _LOGGER.warning(
                "platform_error_envelope.body_read_failed",
                status_code=response.status_code,
            )
            return response

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
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        if not isinstance(decoded, dict):
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
                background=response.background,
            )

        request_id_raw = getattr(request.state, "request_id", None)
        trace_id_raw = getattr(request.state, "trace_id", None)

        company = getattr(request.state, "company", None)
        active_company_id: str | None = None
        if company is not None and hasattr(company, "company_id"):
            cid = getattr(company, "company_id", None)
            if isinstance(cid, str) and cid:
                active_company_id = cid

        settings = get_settings()
        merged = try_merge_platform_error_into_dict(
            decoded,
            trace_id=trace_id_raw if isinstance(trace_id_raw, str) else None,
            platform_request_id=request_id_raw if isinstance(request_id_raw, str) else None,
            service_name=self._service_name,
            logging_cfg=settings.logging,
            active_company_id=active_company_id,
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
