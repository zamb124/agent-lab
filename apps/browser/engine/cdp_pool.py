"""
Пул подключений Playwright к CDP endpoint (Lightpanda / Chromium).

Этот модуль отвечает только за уровень Browser/CDP:
- один общий Playwright driver на процесс;
- одно CDP-подключение (`Browser`) на `endpoint_key`;
- безопасный конкурентный реюз через `asyncio.Lock`.

Изоляция параллельных сценариев обеспечивается не в пуле, а выше:
- `ContextFactory` разводит выполнение по `(endpoint_key, context_signature_hash)`;
- `PageLeaseManager` раздаёт отдельные `page` и учитывает lease/TTL по `session_id`.
Пул не смешивает страницы и сессии между собой: он только выдаёт один и тот же
Browser-объект для endpoint-а.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import Playwright, async_playwright

from apps.browser.engine.cdp_url_normalize import normalize_playwright_cdp_connect_url
from apps.browser.engine.types import BrowserHandle


class CDPConnectionPool:
    """
    Пул CDP-подключений: один Playwright driver на процесс и реюз Browser по `endpoint_key`.

    Мотивация:
    - Убрать дорогой повторный `connect_over_cdp` для каждого запроса.
    - Централизовать lifecycle transport-уровня отдельно от логики сессий/страниц.
    - Избежать гонок при одновременном старте нескольких задач.

    Связи:
    - Используется `PlaywrightBrowserInteractor` для acquire браузера.
    - Используется `CDPLifecycleManagerImpl` для endpoint-level disconnect/stop.

    Состояние:
    - `_playwright`: общий async Playwright instance.
    - `_browsers`: map `endpoint_key -> Browser`.
    - `_lock`: сериализация конкурентного старта/подключения/остановки.

    Инварианты:
    - Для одного `endpoint_key` в пуле существует не более одного Browser объекта.
    - `start()` идемпотентен.
    - `stop()` закрывает все Browser и после этого обнуляет `_playwright`.

    Переиспользование:
    - Стоит: всегда, когда задачи работают через один и тот же CDP endpoint.
    - Не стоит: если нужна жёсткая изоляция по отдельным browser process на задачу —
      в этом случае выдавайте уникальные `endpoint_key`/endpoint-ы на каждый поток.

    Процесс работы (высокоуровнево):
    1) `acquire_browser(endpoint_key, cdp_url)` валидирует аргументы и вызывает `start()`.
    2) Под `_lock` проверяет `_browsers`:
       - если Browser уже есть, возвращает его без нового connect;
       - если нет, делает `connect_over_cdp(cdp_url)`, кладёт в map и возвращает.
    3) Параллельные вызовы с одним `endpoint_key` сериализуются тем же `_lock`,
       поэтому создаётся максимум одно новое подключение.
    4) `disconnect(endpoint_key)` удаляет Browser из map и закрывает только его.
    5) `stop()` закрывает все известные Browser и общий Playwright instance.

    Что это значит для параллельных LLM на одном endpoint:
    - разрешено выполнять несколько сессий одновременно;
    - они делят один Browser/CDP transport;
    - чтобы сессии не мешали друг другу, изоляция должна идти через
      раздельные context/page (это зона `ContextFactory` и `PageLeaseManager`).
    """

    def __init__(self) -> None:
        self._lock: asyncio.Lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._browsers: dict[str, BrowserHandle] = {}

    async def start(self) -> None:
        async with self._lock:
            if self._playwright is None:
                self._playwright = await async_playwright().start()

    async def acquire_browser(self, endpoint_key: str, cdp_url: str) -> BrowserHandle:
        """
        Вернуть Browser для endpoint-а, создав его при первом обращении.

        Поведение конкурентности:
        - критическая секция под `_lock` гарантирует single-connect per endpoint;
        - повторные acquire для того же endpoint возвращают уже подключённый Browser.
        """
        if not endpoint_key:
            raise ValueError("endpoint_key обязателен")
        if not cdp_url:
            raise ValueError("cdp_url обязателен")
        await self.start()
        async with self._lock:
            if self._playwright is None:
                raise RuntimeError("Playwright не инициализирован")
            if endpoint_key in self._browsers:
                return self._browsers[endpoint_key]
            ws_url = await normalize_playwright_cdp_connect_url(cdp_url)
            browser = await self._playwright.chromium.connect_over_cdp(ws_url)
            self._browsers[endpoint_key] = browser
            return browser

    async def disconnect(self, endpoint_key: str) -> None:
        async with self._lock:
            browser = self._browsers.pop(endpoint_key, None)
        if browser is not None:
            await browser.close()

    async def stop(self) -> None:
        async with self._lock:
            browsers = list(self._browsers.values())
            self._browsers.clear()
            pw = self._playwright
            self._playwright = None
        for browser in browsers:
            await browser.close()
        if pw is not None:
            await pw.stop()

    def has_endpoint(self, endpoint_key: str) -> bool:
        return endpoint_key in self._browsers

    @property
    def playwright(self) -> Playwright | None:
        return self._playwright
