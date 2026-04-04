"""
Прокси первого сегмента пути для локальной разработки без общего ingress.

Браузер ходит на тот же origin (например :8002) с путями /flows/..., /crm/...
В development/test при Host localhost или *.lvh.me запрос пересылается на URL из server.*_service_url.
Если текущий процесс уже обслуживает этот сервис (service_name совпадает с первым сегментом), прокси не используется.
"""

from __future__ import annotations

import logging
from typing import FrozenSet
from urllib.parse import urlparse

import httpx
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings
from core.utils.domain import is_local

logger = logging.getLogger(__name__)

_SERVICE_PREFIXES: tuple[str, ...] = ("flows", "crm", "rag", "sync", "documents", "frontend")

# Где публичный первый сегмент пути не совпадает с ключом get_service_url / SERVER__*_SERVICE_URL.
_PREFIX_TO_SERVICE_URL_KEY: dict[str, str] = {
    "documents": "office",
}

_HOP_BY_HOP_REQUEST: FrozenSet[str] = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
    }
)

_EXCLUDED_RESPONSE_HEADERS: FrozenSet[str] = frozenset(
    {
        "connection",
        "content-encoding",
        "content-length",
        "keep-alive",
        "transfer-encoding",
        "server",
    }
)


class DevInterServiceProxyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, service_name: str) -> None:
        super().__init__(app)
        self._service_name = service_name

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.server.env not in ("development", "test"):
            return await call_next(request)

        host = request.headers.get("host") or ""
        if not is_local(host):
            return await call_next(request)

        path = request.scope.get("path") or ""
        parts = [p for p in path.split("/") if p]
        if not parts:
            return await call_next(request)

        target = parts[0]
        if target not in _SERVICE_PREFIXES:
            return await call_next(request)

        if target == self._service_name:
            return await call_next(request)

        url_key = _PREFIX_TO_SERVICE_URL_KEY.get(target, target)
        base = settings.server.get_service_url(url_key).rstrip("/")
        query = request.url.query
        upstream = f"{base}{path}"
        if query:
            upstream = f"{upstream}?{query}"

        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный URL сервиса {url_key} (path {target}): {base!r}")

        # Исходный Host от браузера (qqq.lvh.me:8002), иначе CompanyResolver на flows/crm/rag
        # получает localhost:8001 и теряет субдомен — редирект на select-company.
        upstream_host = (request.headers.get("host") or "").strip() or parsed.netloc

        forward_headers: list[tuple[str, str]] = []
        for key, value in request.headers.items():
            lk = key.lower()
            if lk in _HOP_BY_HOP_REQUEST:
                continue
            if lk == "host":
                continue
            forward_headers.append((key, value))
        forward_headers.append(("host", upstream_host))

        body = await request.body()

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(120.0),
            trust_env=False,
        ) as client:
            upstream_response = await client.request(
                request.method,
                upstream,
                headers=dict(forward_headers),
                content=body if body else None,
            )

        out_headers: dict[str, str] = {}
        for key, value in upstream_response.headers.items():
            if key.lower() in _EXCLUDED_RESPONSE_HEADERS:
                continue
            out_headers[key] = value

        logger.debug(
            "DevInterServiceProxy: %s %s -> %s (%s)",
            request.method,
            path,
            upstream,
            upstream_response.status_code,
        )

        return Response(
            content=upstream_response.content,
            status_code=upstream_response.status_code,
            headers=out_headers,
        )
