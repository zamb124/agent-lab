"""StorefrontHostMiddleware — Host→витрина/агрегатор рерайт на границе сервиса.

На ``*.<storefront_domain_suffix>`` корень ``/`` переписывается на
``/shop/api/v1/public/host`` — единый endpoint, который резолвит slug-витрину,
кастомный домен и поддомен компании внутри ``resolve_shop_by_host``.
``/market`` на любом хосте — страница агрегатора (ingress отдаёт apex
``/market`` прямо в shop). На хосте агрегатора ``shop.<suffix>`` корень —
агрегатор, ``/s/{slug}`` — витрина.
"""

from __future__ import annotations

from core.types import ASGIApp, ASGIReceive, ASGIScope, ASGISend

_STOREFRONT_PAGE = "/shop/api/v1/public/s/"
_HOST_PAGE = "/shop/api/v1/public/host"
_MARKET_PAGE = "/shop/api/v1/public/market"
_PUBLIC_FILES: dict[str, str] = {
    "/robots.txt": "/shop/api/v1/public/robots.txt",
    "/sitemap.xml": "/shop/api/v1/public/sitemap.xml",
}


class StorefrontHostMiddleware:
    """Рерайт корня suffix-хоста на витрину, ``/market`` и хоста агрегатора — на market."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        domain_suffix: str,
        aggregator_host: str,
    ) -> None:
        self._app: ASGIApp = app
        self._suffix: str = f".{domain_suffix}" if domain_suffix else ""
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
        if scope.get("method") not in ("GET", "HEAD"):
            await self._app(scope, receive, send)
            return
        is_aggregator = self._aggregator and host == self._aggregator
        if is_aggregator and isinstance(path, str) and path.startswith("/s/"):
            slug = path[3:].split("/", 1)[0]
            if slug:
                scope["path"] = f"{_STOREFRONT_PAGE}{slug}"
                await self._app(scope, receive, send)
                return
        if path == "/market":
            scope["path"] = _MARKET_PAGE
            await self._app(scope, receive, send)
            return
        if not host.endswith(self._suffix):
            await self._app(scope, receive, send)
            return
        if path == "/":
            scope["path"] = _MARKET_PAGE if is_aggregator else _HOST_PAGE
        elif isinstance(path, str) and path in _PUBLIC_FILES:
            scope["path"] = _PUBLIC_FILES[path]
        await self._app(scope, receive, send)
