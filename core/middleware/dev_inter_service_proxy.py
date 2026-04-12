"""
Прокси первого сегмента пути для локальной разработки без общего ingress.

Браузер ходит на тот же origin (например :8002) с путями /flows/..., /crm/...
В development/test при Host localhost или *.lvh.me запрос пересылается на URL из server.*_service_url.
Если текущий процесс уже обслуживает этот сервис (первый сегмент пути совпадает с именем процесса
или с публичным префиксом из _PREFIX_TO_SERVICE_URL_KEY, например office и /documents/...), прокси не используется.

OnlyOffice: префиксы /web-apps, /common, /cache, /fonts, /sdkjs, /downloadfile и пути
/{semver}-{hex}/web-apps/..., /{semver}-{hex}/sdkjs/..., /{semver}-{hex}/fonts/..., /{semver}-{hex}/doc/... (co-editing)
при server.document_server_dev_upstream_url проксируются на Document Server. Host к upstream — тот же, что у браузера (shell),
иначе DS подставляет netloc контейнера в подписанные URL (/cache/...) и ловится CORS.
"""

from __future__ import annotations

import logging
import re
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

_ONLYOFFICE_STATIC_SEGMENTS: frozenset[str] = frozenset(
    {"web-apps", "common", "cache", "fonts", "sdkjs"},
)

# Сессии редактора: POST/GET у корня хоста DS, не под /web-apps/
_ONLYOFFICE_DS_ROOT_SEGMENTS: frozenset[str] = frozenset(
    {"downloadfile"},
)

# DS (7.3+): под /{semver}-{hex}/ — web-apps, sdkjs, fonts, doc (шрифты и статика не только под /fonts/)
_ONLYOFFICE_VERSIONED_DS_PREFIX: re.Pattern[str] = re.compile(
    r"^/[0-9]+\.[0-9]+\.[0-9]+-[a-f0-9]+/(?:web-apps|sdkjs|fonts|doc)(?:/|$)",
    re.IGNORECASE,
)


def _is_onlyoffice_upstream_path(path: str) -> bool:
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] in _ONLYOFFICE_STATIC_SEGMENTS:
        return True
    if parts and parts[0] in _ONLYOFFICE_DS_ROOT_SEGMENTS:
        return True
    return _ONLYOFFICE_VERSIONED_DS_PREFIX.match(path) is not None


def _is_local_target_for_process(first_path_segment: str, process_service_name: str) -> bool:
    """True — запрос с таким первым сегментом должен обработать текущий процесс без HTTP-прокси."""
    if first_path_segment == process_service_name:
        return True
    if _PREFIX_TO_SERVICE_URL_KEY.get(first_path_segment) == process_service_name:
        return True
    return False


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

    async def _forward_http(
        self,
        request: Request,
        *,
        upstream_base: str,
        path: str,
        upstream_host: str,
    ) -> Response:
        base = upstream_base.rstrip("/")
        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный upstream base: {upstream_base!r}")

        query = request.url.query
        upstream = f"{base}{path}"
        if query:
            upstream = f"{upstream}?{query}"

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
        if _is_onlyoffice_upstream_path(path):
            ds_base = (settings.server.document_server_dev_upstream_url or "").strip().rstrip("/")
            if not ds_base:
                return await call_next(request)
            parsed_ds = urlparse(ds_base)
            if not parsed_ds.netloc:
                raise RuntimeError(f"Некорректный server.document_server_dev_upstream_url: {ds_base!r}")
            client_host = (request.headers.get("host") or "").strip() or parsed_ds.netloc
            return await self._forward_http(
                request,
                upstream_base=ds_base,
                path=path,
                upstream_host=client_host,
            )

        if target not in _SERVICE_PREFIXES:
            return await call_next(request)

        if _is_local_target_for_process(target, self._service_name):
            return await call_next(request)

        url_key = _PREFIX_TO_SERVICE_URL_KEY.get(target, target)
        base = settings.server.get_service_url(url_key).rstrip("/")
        parsed = urlparse(base)
        if not parsed.netloc:
            raise RuntimeError(f"Некорректный URL сервиса {url_key} (path {target}): {base!r}")

        upstream_host = (request.headers.get("host") or "").strip() or parsed.netloc

        return await self._forward_http(
            request,
            upstream_base=base,
            path=path,
            upstream_host=upstream_host,
        )
