"""Dynamic CORS для embed A2A endpoint по EmbedConfig.allowed_origins."""

from __future__ import annotations

from typing import override

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

from apps.flows.src.container import FlowContainer
from apps.flows.src.services.embed_target_resolver import resolve_embed_target


class EmbedDynamicCorsMiddleware(BaseHTTPMiddleware):
    """Обрабатывает CORS для embed A2A и его узкого interface-profile."""

    _EMBED_PREFIX: str = "/flows/api/v1/embed/"
    _EMBED_SUBPATHS: frozenset[str] = frozenset({"interface-profile"})

    def __init__(self, app: ASGIApp, *, container: FlowContainer) -> None:
        super().__init__(app)
        self._container: FlowContainer = container

    @override
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        embed_id = self._extract_embed_id(request.url.path)
        if embed_id is None:
            return await call_next(request)

        origin = (request.headers.get("origin") or "").strip()
        target = await resolve_embed_target(self._container, embed_id)
        if target is None:
            return JSONResponse(status_code=404, content={"detail": "Embed config not found"})
        if not target.active:
            return JSONResponse(status_code=403, content={"detail": "Embed config disabled"})

        if request.method.upper() == "OPTIONS":
            if not origin:
                return Response(status_code=400)
            if not _is_origin_allowed(origin, target.allowed_origins):
                return Response(status_code=403)
            response = Response(status_code=204)
            _apply_cors_headers(response, origin)
            return response

        if origin and not _is_origin_allowed(origin, target.allowed_origins):
            return JSONResponse(status_code=403, content={"detail": "origin не разрешен для этой конфигурации"})

        response = await call_next(request)
        if origin and _is_origin_allowed(origin, target.allowed_origins):
            _apply_cors_headers(response, origin)
        return response

    @classmethod
    def _extract_embed_id(cls, path: str) -> str | None:
        if not path.startswith(cls._EMBED_PREFIX):
            return None
        suffix = path[len(cls._EMBED_PREFIX):].strip("/")
        if not suffix:
            return None
        if "/" not in suffix:
            return suffix
        embed_id, _, subpath = suffix.partition("/")
        if embed_id and subpath in cls._EMBED_SUBPATHS:
            return embed_id
        return None


def _is_origin_allowed(origin: str, allowed_origins: list[str]) -> bool:
    if not allowed_origins:
        return True
    return origin in allowed_origins


_EMBED_CORS_ALLOW_HEADERS = (
    "Accept, Authorization, Content-Type, A2A-Version, A2A-Extensions, "
    "X-Platform-Namespace, X-Test-Scope"
)


def _apply_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    # browser chat шлёт A2A-Version (+ Accept) на POST /embed/{id}; иначе preflight CORS fail
    response.headers["Access-Control-Allow-Headers"] = _EMBED_CORS_ALLOW_HEADERS
    response.headers["Vary"] = "Origin"
