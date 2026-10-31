"""StorefrontHostMiddleware — Host→slug рерайт для витрин на wildcard-поддоменах.

На ``<slug>.<storefront_domain_suffix>`` корень ``/`` переписывается на
``/shop/api/v1/public/s/{slug}`` — анонимный SSR-lite storefront shell.
Агрегатор ``shop.<suffix>`` и платформенные хосты не трогаются. Кастомные
домены резолвятся API-эндпоинтом ``/public/resolve`` после DNS-провиженинга.
"""

from __future__ import annotations

from core.types import ASGIApp, ASGIReceive, ASGIScope, ASGISend

_STOREFRONT_PAGE = "/shop/api/v1/public/s/"


class StorefrontHostMiddleware:
    """Рерайт корня slug-поддомена на страницу витрины."""

    def __init__(self, app: ASGIApp, *, domain_suffix: str, reserved: frozenset[str]) -> None:
        self._app: ASGIApp = app
        self._suffix: str = f".{domain_suffix}" if domain_suffix else ""
        self._reserved: frozenset[str] = reserved

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http" or not self._suffix:
            await self._app(scope, receive, send)
            return
        host = ""
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = value.decode("latin-1").split(":")[0].strip().lower()
                break
        slug = self._slug_for(host)
        if slug is not None and scope.get("method") in ("GET", "HEAD") and scope.get("path") == "/":
            scope["path"] = f"{_STOREFRONT_PAGE}{slug}"
        await self._app(scope, receive, send)

    def _slug_for(self, host: str) -> str | None:
        if not host.endswith(self._suffix):
            return None
        candidate = host[: -len(self._suffix)]
        if not candidate or "." in candidate or candidate in self._reserved:
            return None
        return candidate
