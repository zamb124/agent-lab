"""StorefrontHostMiddleware — Host→slug рерайт для витрин на wildcard-поддоменах.

На ``<slug>.<storefront_domain_suffix>`` корень ``/`` переписывается на
``/shop/api/v1/public/s/{slug}`` — анонимный SSR-lite storefront shell.
Агрегатор ``shop.<suffix>`` и платформенные хосты не трогаются. Кастомные
домены резолвятся API-эндпоинтом ``/public/resolve`` после DNS-провиженинга.
"""

from __future__ import annotations

from core.types import ASGIApp, ASGIReceive, ASGIScope, ASGISend

_STOREFRONT_PAGE = "/shop/api/v1/public/s/"
_MARKET_PAGE = "/shop/api/v1/public/market"
_PUBLIC_FILES: dict[str, str] = {
    "/robots.txt": "/shop/api/v1/public/robots.txt",
    "/sitemap.xml": "/shop/api/v1/public/sitemap.xml",
}


class StorefrontHostMiddleware:
    """Рерайт корня slug-поддомена на страницу витрины, хоста агрегатора — на market."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        domain_suffix: str,
        reserved: frozenset[str],
        aggregator_host: str,
    ) -> None:
        self._app: ASGIApp = app
        self._suffix: str = f".{domain_suffix}" if domain_suffix else ""
        self._reserved: frozenset[str] = reserved
        self._aggregator: str = aggregator_host.strip().lower()

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http" or not self._suffix:
            await self._app(scope, receive, send)
            return
        host = ""
        for name, value in scope.get("headers", []):
            if name == b"host":
                host = value.decode("latin-1").split(":")[0].strip().lower()
                break
        path = scope.get("path")
        if scope.get("method") not in ("GET", "HEAD") or not host.endswith(self._suffix):
            await self._app(scope, receive, send)
            return
        if path == "/":
            if self._aggregator and host == self._aggregator:
                scope["path"] = _MARKET_PAGE
            else:
                slug = self._slug_for(host)
                if slug is not None:
                    scope["path"] = f"{_STOREFRONT_PAGE}{slug}"
        elif isinstance(path, str) and path in _PUBLIC_FILES:
            scope["path"] = _PUBLIC_FILES[path]
        await self._app(scope, receive, send)

    def _slug_for(self, host: str) -> str | None:
        if not host.endswith(self._suffix):
            return None
        candidate = host[: -len(self._suffix)]
        if not candidate or "." in candidate or candidate in self._reserved:
            return None
        return candidate
