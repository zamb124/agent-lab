"""ASGI-middleware SEO-аналитики: событие ``seo.visit`` на визит публичной поверхности.

Ставится через ``extra_middlewares`` фабрики — выполняется до ProxyHeaders,
поэтому клиентский IP читается из ``x-forwarded-for`` напрямую. В лог уходят
только публичные GET/HEAD (``surface_of``): внутренний рендер снапшотов
(``spa_shell=1``, UA headless-слоя) и служебные ``/frontend/*`` не считаются
визитами. Сырой IP не пишется — идентичность посетителя это HMAC(ip|ua) от
``auth.jwt_secret_key``: повторные визиты связываются, PII не утекает.

GeoIP-база прогревается в ``frontend_startup`` (точно до первого запроса,
загрузка ~1с синхронна и в event loop недопустима); ``geoip.enabled`` без
файла базы — падение стартапа, не деградация визитов.
"""

from __future__ import annotations

from apps.frontend.config import FrontendSettings, get_frontend_settings
from apps.frontend.seo.analytics import (
    classify_ua,
    locale_of,
    referer_host,
    surface_of,
    visitor_id,
)
from core.geoip import GeoIpResolver, get_geoip_resolver
from core.logging import get_logger
from core.types import ASGIApp, ASGIReceive, ASGIScope, ASGISend

logger = get_logger(__name__)


def _header(scope: ASGIScope, name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return value.decode("latin-1")
    return ""


def _client_ip(scope: ASGIScope) -> str:
    forwarded = _header(scope, b"x-forwarded-for")
    if forwarded:
        return forwarded.split(",", 1)[0].strip()
    client = scope.get("client")
    if isinstance(client, tuple) and client and isinstance(client[0], str):
        return client[0]
    return ""


class SeoAnalyticsMiddleware:
    """Логирует ``seo.visit``: surface/path/locale, страна, UA-семейство, referer."""

    def __init__(self, app: ASGIApp) -> None:
        self._app: ASGIApp = app
        settings = get_frontend_settings()
        self._settings: FrontendSettings = settings
        self._resolver: GeoIpResolver | None = (
            get_geoip_resolver(settings.geoip) if settings.geoip.enabled else None
        )
        self._salt_missing_logged: bool = False

    async def __call__(self, scope: ASGIScope, receive: ASGIReceive, send: ASGISend) -> None:
        if scope["type"] != "http" or scope.get("method") not in ("GET", "HEAD"):
            await self._app(scope, receive, send)
            return
        path = scope.get("path")
        if not isinstance(path, str):
            await self._app(scope, receive, send)
            return
        surface = surface_of(path)
        if surface is None:
            await self._app(scope, receive, send)
            return
        if b"spa_shell=1" in scope.get("query_string", b""):
            await self._app(scope, receive, send)
            return
        ua = _header(scope, b"user-agent")
        family, is_bot = classify_ua(ua)
        if family == "internal-renderer":
            # Пререндер снапшотов browser-сервисом — не визит.
            await self._app(scope, receive, send)
            return
        ip = _client_ip(scope)
        salt = self._settings.auth.jwt_secret_key
        if salt is None:
            if not self._salt_missing_logged:
                logger.error("seo.analytics.jwt_secret_missing")
                self._salt_missing_logged = True
            visitor = ""
        else:
            visitor = visitor_id(ip, ua, salt)
        logger.info(
            "seo.visit",
            surface=surface,
            path=path,
            locale=locale_of(path),
            host=_header(scope, b"host").split(":", 1)[0],
            country=self._resolver.country_of(ip) if self._resolver and ip else "",
            ua_family=family,
            bot=is_bot,
            referer=referer_host(_header(scope, b"referer")),
            visitor=visitor,
        )
        await self._app(scope, receive, send)
