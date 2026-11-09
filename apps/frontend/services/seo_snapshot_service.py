"""Runtime-пререндер публичных страниц: DSD-снапшоты через apps/browser + Redis-кэш.

Снапшот — это ответ всем (не только ботам): краулеры и LLM-боты получают
полный HTML с контентом, JSON-LD и hreflang, пользователи — мгновенный
first paint с последующей lit-гидратацией.

Ключ кэша включает ``deployment_version`` — выкат нового бандла автоматически
инвалидирует снапшоты без ручной чистки. При недоступности browser-сервиса
возвращается ``None`` и ``serve_spa`` отдаёт обычную оболочку (fail-open).
"""

from __future__ import annotations

import asyncio

from apps.frontend.config import FrontendSettings
from apps.frontend.seo.pages import (
    PUBLIC_PAGES,
    SEO_LOCALES,
    PublicPage,
    SeoLocale,
    localized_marketing_path,
)
from apps.frontend.seo.postprocess import postprocess_snapshot
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.platform_brand.resolver import (
    platform_public_base_url,
    resolve_brand_or_primary,
    resolve_seo_base_url,
)

logger = get_logger(__name__)

# Маркер: serve_spa по этому query-параметру отдаёт оболочку, не снапшот —
# без него пререндер пошёл бы в собственный endpoint и зациклился.
SNAPSHOT_BYPASS_PARAM = "spa_shell"

_SNAPSHOT_TTL_SECONDS = 6 * 60 * 60
_SNAPSHOT_FAIL_TTL_SECONDS = 60
# Дольше максимального fetch (nav 30s + service timeout 45s), чтобы лидер
# успел закончить до истечения блокировки.
_SNAPSHOT_LOCK_TTL_SECONDS = 60
_SNAPSHOT_NAV_TIMEOUT_MS = 30_000
_SNAPSHOT_SERVICE_TIMEOUT_SECONDS = 45.0
# i18n-бандлы и API грузятся fetch/xhr — блокируем только не влияющее на DOM.
_SNAPSHOT_BLOCK_RESOURCES = ["image", "media", "font", "eventsource", "websocket", "manifest"]


class SeoSnapshotService:
    def __init__(
        self,
        browser_fetch_client: BrowserFetchClient,
        redis_client: RedisClient,
        frontend_settings: FrontendSettings,
    ) -> None:
        self._browser: BrowserFetchClient = browser_fetch_client
        self._redis: RedisClient = redis_client
        self._settings: FrontendSettings = frontend_settings

    @staticmethod
    def _normalized(path: str) -> str:
        """Сегмент ключа для пути: ``""`` (корень) → ``root``."""
        stripped = path.strip("/")
        return stripped if stripped else "root"

    def _cache_key(self, path: str, locale: str) -> str:
        version = self._settings.server.deployment_version
        version_key = version if version else "dev"
        return f"seo:snap:{version_key}:{locale}:{self._normalized(path)}"

    def _fail_key(self, path: str, locale: str) -> str:
        return f"seo:snap:fail:{locale}:{self._normalized(path)}"

    def _lock_key(self, path: str, locale: str) -> str:
        return f"seo:snap:lock:{locale}:{self._normalized(path)}"

    async def _mark_failure(self, page: PublicPage, locale: str) -> None:
        try:
            _ = await self._redis.set(
                self._fail_key(page.path, locale), "1", ttl=_SNAPSHOT_FAIL_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("seo.snapshot.fail_mark_failed", error=str(exc))

    def _fetch_base(self) -> str:
        # Рендер по публичному origin, а не по внутреннему service-адресу:
        # SPA читает бренд из Host — на service-хосте bootstrap не резолвится
        # и страница не доходит до wait_selector. Canonical origin проходит
        # тем же путём, что и реальный посетитель (ingress → serve_spa);
        # ``spa_shell`` исключает рекурсию снапшота.
        return platform_public_base_url().rstrip("/")

    def _fetch_url(self, path: str, locale: SeoLocale) -> str:
        localized = localized_marketing_path(path, locale)
        suffix = f"/{localized}" if localized else "/"
        return f"{self._fetch_base()}{suffix}?{SNAPSHOT_BYPASS_PARAM}=1"

    async def snapshot_html(self, page: PublicPage, locale: SeoLocale) -> str | None:
        """Пререндеренный HTML страницы; ``None`` — снапшот недоступен (fail-open)."""
        key = self._cache_key(page.path, locale)
        try:
            cached = await self._redis.get(key)
        except Exception as exc:
            logger.warning("seo.snapshot.cache_get_failed", error=str(exc))
            cached = None
        if cached:
            return cached

        try:
            if await self._redis.get(self._fail_key(page.path, locale)):
                return None
        except Exception as exc:
            logger.warning("seo.snapshot.fail_get_failed", error=str(exc))

        # Не плодим параллельные fetch на одну страницу: лидер рендерит,
        # остальные получают оболочку — следующий хит заберёт готовый кэш.
        lock_key = self._lock_key(page.path, locale)
        try:
            acquired = await self._redis.set_nx(
                lock_key, "1", ttl_seconds=_SNAPSHOT_LOCK_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("seo.snapshot.lock_failed", error=str(exc))
            acquired = True
        if not acquired:
            return None

        try:
            try:
                response = await self._browser.fetch_html(
                    self._fetch_url(page.path, locale),
                    timeout_ms=_SNAPSHOT_NAV_TIMEOUT_MS,
                    service_timeout_seconds=_SNAPSHOT_SERVICE_TIMEOUT_SECONDS,
                    locale="en-US" if locale == "en" else "ru-RU",
                    wait_selector=page.wait_selector,
                    html_capture="dsd",
                    block_resource_types=list(_SNAPSHOT_BLOCK_RESOURCES),
                )
            except Exception as exc:
                logger.warning(
                    "seo.snapshot.fetch_failed",
                    path=page.path,
                    locale=locale,
                    error=str(exc),
                )
                await self._mark_failure(page, locale)
                return None

            try:
                html = postprocess_snapshot(
                    response.html,
                    page=page,
                    locale=locale,
                    brand=resolve_brand_or_primary(None),
                    seo_base_url=resolve_seo_base_url(),
                )
            except Exception as exc:
                logger.warning(
                    "seo.snapshot.postprocess_failed",
                    path=page.path,
                    locale=locale,
                    error=str(exc),
                )
                await self._mark_failure(page, locale)
                return None
            try:
                _ = await self._redis.set(key, html, ttl=_SNAPSHOT_TTL_SECONDS)
            except Exception as exc:
                logger.warning("seo.snapshot.cache_set_failed", error=str(exc))
            return html
        finally:
            # Лидер закончил: снимаем lock, чтобы ретрай не ждал TTL.
            # Cache set уже отработал либо fail-маркер поставлен — дублей нет.
            try:
                _ = await self._redis.delete(lock_key)
            except Exception as exc:
                logger.warning("seo.snapshot.lock_release_failed", error=str(exc))

    async def invalidate(self, path: str, locale: str) -> None:
        _ = await self._redis.delete(self._cache_key(path, locale), self._fail_key(path, locale))

    async def _warmup_pass(
        self, pending: list[tuple[PublicPage, SeoLocale]]
    ) -> list[tuple[PublicPage, SeoLocale]]:
        missed: list[tuple[PublicPage, SeoLocale]] = []
        for page, locale in pending:
            try:
                html = await self.snapshot_html(page, locale)
            except Exception as exc:
                html = None
                logger.warning(
                    "seo.snapshot.warmup_page_failed",
                    path=page.path,
                    locale=locale,
                    error=str(exc),
                )
            if html is None:
                missed.append((page, locale))
        return missed

    async def warmup_public_pages(self) -> None:
        """Прогрев кэша снапшотов: все публичные страницы в обеих локалях.

        Первый проход на холодном выкате может попасть в окно, когда ingress
        ещё не отдаёт canonical origin (сам сервис стартует) — промахи
        перепроверяются одним повторным проходом после паузы, равной TTL
        fail-маркера. Итог логируется ``seo.snapshot.warmup_failed`` только
        по устойчивым промахам — это alertable-сигнал «пререндер деградировал»
        (warning-алерт ``seo-snapshot-failures`` в Grafana).
        """
        pending: list[tuple[PublicPage, SeoLocale]] = [
            (page, locale) for page in PUBLIC_PAGES for locale in SEO_LOCALES
        ]
        total = len(pending)
        missed = await self._warmup_pass(pending)
        if missed:
            await asyncio.sleep(_SNAPSHOT_FAIL_TTL_SECONDS)
            missed = await self._warmup_pass(missed)
        if missed:
            logger.error("seo.snapshot.warmup_failed", failed=len(missed), total=total)
        else:
            logger.info("seo.snapshot.warmup_ok", warmed=total)
