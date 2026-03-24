"""
Заголовки деплоя и сброс кэша браузера для статики и HTML (не для REST /api).
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import get_settings


def _should_set_no_cache(path: str) -> bool:
    if path in ("/health",) or path.endswith("/health"):
        return False
    if path.endswith("/openapi.json"):
        return False
    if "/api/" in path:
        return False
    if path in ("/docs", "/redoc"):
        return False
    if path.endswith("/docs") or path.endswith("/redoc"):
        return False
    if path.endswith("/ws") or "/ws/" in path:
        return False
    return True


class DeploymentHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        settings = get_settings()
        version = settings.server.deployment_version
        if version:
            response.headers["X-Deployment-Version"] = version
        if request.method == "GET" and _should_set_no_cache(request.url.path):
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response
