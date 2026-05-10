"""
CORS заголовки для cross-origin загрузки ES modules с префикса /static/core (embed-виджет).
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

STATIC_CORE_PREFIX = "/static/core"


class StaticCoreModuleCorsMiddleware(BaseHTTPMiddleware):
    """Добавляет Access-Control-Allow-Origin для статики core-frontend без учёта общего CORSMiddleware."""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if not path.startswith(STATIC_CORE_PREFIX):
            return await call_next(request)

        if request.method.upper() == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "access-control-allow-origin": "*",
                    "access-control-allow-methods": "GET, HEAD, OPTIONS",
                    "access-control-allow-headers": "*",
                    "access-control-max-age": "86400",
                },
            )

        response = await call_next(request)
        if response.headers.get("access-control-allow-origin") is None:
            response.headers["Access-Control-Allow-Origin"] = "*"
        return response
