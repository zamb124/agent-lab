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
from core.clients.browser.crawl_fetch_types import BrowserCrawlFetchResponse
from core.clients.browser_fetch_client import BrowserFetchClient
from core.clients.redis_client import RedisClient
from core.clients.service_client import ServiceClientError
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
# Stale-слой живёт намного дольше свежего ключа: при истечении TTL,
# холодном выкате или фейле рендера краулер получает последний удачный
# DSD-контент, а не оболочку — классический stale-while-revalidate.
_SNAPSHOT_STALE_TTL_SECONDS = 7 * 24 * 60 * 60
_SNAPSHOT_FAIL_TTL_SECONDS = 60
# Дольше максимального fetch (nav 30s + service timeout 45s), чтобы лидер
# успел закончить до истечения блокировки.
_SNAPSHOT_LOCK_TTL_SECONDS = 60
# Прогрев раз в час; страницы с остаточным TTL ниже половины снапшотного
# перерендериваются упреждающе — кэш публичных страниц не истекает вообще,
# и ленивый хит никогда не ждёт живой DSD-рендер.
_WARMUP_INTERVAL_SECONDS = 60 * 60
_WARMUP_REFRESH_TTL_FLOOR = _SNAPSHOT_TTL_SECONDS // 2
_SNAPSHOT_NAV_TIMEOUT_MS = 30_000
_SNAPSHOT_SERVICE_TIMEOUT_SECONDS = 45.0
# 429 — контракт backpressure browser-сервиса: семафор краулера занят на
# секунды, а мгновенный fail-marker превращал бы транзитную конкуренцию в
# минуту stale-отдач. Ретраим только явный rate-limit (отказ мгновенный,
# попытка почти бесплатна); таймауты и 5xx рендера — в fail-путь сразу.
_SNAPSHOT_FETCH_429_DELAYS = (2.0, 4.0, 8.0)
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

    def _stale_key(self, path: str, locale: str) -> str:
        return f"seo:snapstale:{locale}:{self._normalized(path)}"

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

    async def _stale_snapshot(self, page: PublicPage, locale: SeoLocale) -> str | None:
        """Последний удачный снапшот страницы любой версии — слой SWR.

        Отдельный ключ ``seo:snapstale`` переживает и TTL свежего ключа, и
        смену deployment_version: пока страница хоть раз отрендерилась,
        промах никогда не превращается в оболочку.
        """
        try:
            return await self._redis.get(self._stale_key(page.path, locale))
        except Exception as exc:
            logger.warning("seo.snapshot.stale_get_failed", error=str(exc))
            return None

    async def _render_store(self, page: PublicPage, locale: SeoLocale) -> str | None:
        """Живой рендер → postprocess → запись свежего и stale ключей."""
        try:
            response = await self._fetch_render(page, locale)
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
            _ = await self._redis.set(
                self._cache_key(page.path, locale), html, ttl=_SNAPSHOT_TTL_SECONDS
            )
            _ = await self._redis.set(
                self._stale_key(page.path, locale), html, ttl=_SNAPSHOT_STALE_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("seo.snapshot.cache_set_failed", error=str(exc))
        return html

    async def snapshot_html(
        self, page: PublicPage, locale: SeoLocale, *, force_refresh: bool = False
    ) -> str | None:
        """Пререндеренный HTML страницы; ``None`` — снапшот недоступен (fail-open).

        ``force_refresh`` — путь warmup: ключ жив, но TTL ниже половины —
        чтение из кэша пропускаем и перерендериваем упреждающе, пока
        свежий ключ не истёк (иначе warmup лишь перечитывает свой же кэш
        и весь реестр истекает одной массой).
        """
        key = self._cache_key(page.path, locale)
        if not force_refresh:
            try:
                cached = await self._redis.get(key)
            except Exception as exc:
                logger.warning("seo.snapshot.cache_get_failed", error=str(exc))
                cached = None
            if cached:
                return cached

        stale = await self._stale_snapshot(page, locale)

        if not force_refresh:
            try:
                if await self._redis.get(self._fail_key(page.path, locale)):
                    return stale
            except Exception as exc:
                logger.warning("seo.snapshot.fail_get_failed", error=str(exc))

        # Не плодим параллельные fetch на одну страницу: лидер рендерит,
        # остальные получают stale/оболочку — следующий хит заберёт готовый кэш.
        lock_key = self._lock_key(page.path, locale)
        try:
            acquired = await self._redis.set_nx(
                lock_key, "1", ttl_seconds=_SNAPSHOT_LOCK_TTL_SECONDS
            )
        except Exception as exc:
            logger.warning("seo.snapshot.lock_failed", error=str(exc))
            acquired = True
        if not acquired:
            return stale

        try:
            html = await self._render_store(page, locale)
            return html if html is not None else stale
        finally:
            # Лидер закончил: снимаем lock, чтобы ретрай не ждал TTL.
            # Cache set уже отработал либо fail-маркер поставлен — дублей нет.
            try:
                _ = await self._redis.delete(lock_key)
            except Exception as exc:
                logger.warning("seo.snapshot.lock_release_failed", error=str(exc))

    async def _fetch_render(self, page: PublicPage, locale: SeoLocale) -> BrowserCrawlFetchResponse:
        last_rate_limit: ServiceClientError | None = None
        for attempt, delay in enumerate(_SNAPSHOT_FETCH_429_DELAYS):
            if attempt:
                await asyncio.sleep(delay)
            try:
                return await self._browser.fetch_html(
                    self._fetch_url(page.path, locale),
                    timeout_ms=_SNAPSHOT_NAV_TIMEOUT_MS,
                    service_timeout_seconds=_SNAPSHOT_SERVICE_TIMEOUT_SECONDS,
                    locale="en-US" if locale == "en" else "ru-RU",
                    wait_selector=page.wait_selector,
                    html_capture="dsd",
                    block_resource_types=list(_SNAPSHOT_BLOCK_RESOURCES),
                )
            except ServiceClientError as exc:
                if exc.status_code != 429:
                    raise
                last_rate_limit = exc
        assert last_rate_limit is not None
        raise last_rate_limit

    async def invalidate(self, path: str, locale: str) -> None:
        _ = await self._redis.delete(
            self._cache_key(path, locale),
            self._stale_key(path, locale),
            self._fail_key(path, locale),
        )

    async def _needs_refresh(self, page: PublicPage, locale: SeoLocale) -> bool:
        """Кэш отсутствует или близок к истечению — страницу надо рендерить."""
        try:
            ttl = await self._redis.ttl(self._cache_key(page.path, locale))
        except Exception as exc:
            logger.warning("seo.snapshot.ttl_failed", error=str(exc))
            return True
        return ttl < _WARMUP_REFRESH_TTL_FLOOR

    async def _warmup_pass(
        self, pending: list[tuple[PublicPage, SeoLocale]]
    ) -> list[tuple[PublicPage, SeoLocale]]:
        missed: list[tuple[PublicPage, SeoLocale]] = []
        for page, locale in pending:
            if not await self._needs_refresh(page, locale):
                continue
            try:
                html = await self.snapshot_html(page, locale, force_refresh=True)
            except Exception as exc:
                html = None
                logger.warning(
                    "seo.snapshot.warmup_page_failed",
                    path=page.path,
                    locale=locale,
                    error=str(exc),
                )
            # stale-отдача — не прогрев: ключа новой версии не записано,
            # страница остаётся в missed и уходит в повторный проход,
            # иначе warmup_ok врёт и холодные ключи висят до следующего часа.
            if html is None or await self._needs_refresh(page, locale):
                missed.append((page, locale))
        return missed

    async def _warmup_cycle(self) -> None:
        """Один цикл прогрева: весь реестр + повтор по промахам после паузы."""
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

    async def warmup_public_pages(self) -> None:
        """Периодический прогрев кэша снапшотов: реестр × локали, раз в час.

        Первый проход на холодном выкате может попасть в окно, когда ingress
        ещё не отдаёт canonical origin (сам сервис стартует) — промахи
        перепроверяются одним повторным проходом после паузы, равной TTL
        fail-маркера. Дальнейшие циклы держат кэш вечно горячим: страницы с
        остаточным TTL ниже половины снапшотного перерендериваются раньше
        истечения — ленивый хит живого рендера исключён. Итог каждого цикла
        логируется ``seo.snapshot.warmup_failed`` только по устойчивым
        промахам — alertable-сигнал (алерт ``seo-snapshot-failures``).
        """
        while True:
            try:
                await self._warmup_cycle()
            except Exception as exc:
                logger.error(
                    "seo.snapshot.warmup_cycle_failed",
                    **{"exception.type": type(exc).__name__},
                    error=str(exc),
                )
            await asyncio.sleep(_WARMUP_INTERVAL_SECONDS)
