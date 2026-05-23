"""
Адаптер Playwright: делегирование BrowserInteractor и AX visibility с лимитом budget.
"""

from __future__ import annotations

from apps.browser.contracts.control_types import BrowserCapabilityError, BrowserControlFeatures
from apps.browser.contracts.runtime import BrowserInteractor
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserPage,
)
from core.types import JsonObject


class PlaywrightAdapter:
    """
    Рабочая реализация `BrowserControlAdapter` на базе `BrowserInteractor`.

    Связи:
    - Делегирует start/navigate/stop в interactor.
    - Явно запрещает legacy action-выполнение произвольного кода.
    - Строит visibility/accessibility/listeners через AX/CDP утилиты.

    Состояние:
    - Ссылка на interactor конкретного runtime.

    Инварианты:
    - `features()` правдиво описывает доступные возможности Playwright backend-а.
    - Ошибки CDP listeners маппятся в `BrowserCapabilityError`.

    Мотивация:
    - Отделить внешний control-контракт от деталей Playwright/AX/CDP.

    Переиспользование:
    - Стоит: как основной production-адаптер для CDP-совместимых движков.
    - Не стоит: для backend-а без Playwright API; тогда нужен отдельный адаптер.
    """
    def __init__(self, interactor: BrowserInteractor) -> None:
        self._interactor: BrowserInteractor = interactor

    def features(self) -> BrowserControlFeatures:
        return BrowserControlFeatures(
            supports_js_injection_dom_tree=True,
            supports_cdp_dom_snapshot=True,
            supports_cdp_event_listeners=True,
            supports_ax_tree=True,
            supports_selector_map=False,
        )

    async def start(self, req: BrowserAcquireRequest) -> BrowserAcquireResult:
        return await self._interactor.acquire(req)

    async def navigate(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult:
        return await self._interactor.fetch(page, req)

    async def run_action(self, page: BrowserPage, code: str, *, timeout_ms: int) -> JsonObject:
        _ = page, code, timeout_ms
        raise BrowserCapabilityError(
            code="browser_action_disabled",
            message=(
                "Arbitrary in-process browser actions are disabled; "
                "use navigate/observe/click/fill/press/wait control operations."
            ),
        )

    async def stop(self, page: BrowserPage) -> None:
        await self._interactor.release(page)
