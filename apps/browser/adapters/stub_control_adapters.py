"""
Заглушки BrowserUse / AgentBrowser: контракт без реального backend (Модуль 02).
"""

from __future__ import annotations

from apps.browser.contracts.control_types import BrowserCapabilityError, BrowserControlFeatures
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserPage,
)
from core.types import JsonObject


class BrowserUseAdapter:
    """
    Заглушка backend-а browser-use.

    Связи:
    - Используется factory при `control_backend="browser_use"`.

    Инварианты:
    - Любая активная операция (кроме `stop`) завершается `BrowserCapabilityError`.

    Мотивация:
    - Сохранить контракт API неизменным до готовности реальной интеграции.

    Переиспользование:
    - Стоит: временно в окружениях, где backend явно выключен.
    - Не стоит: как рабочий backend.
    """
    def features(self) -> BrowserControlFeatures:
        return BrowserControlFeatures(
            supports_js_injection_dom_tree=False,
            supports_cdp_dom_snapshot=False,
            supports_cdp_event_listeners=False,
            supports_ax_tree=False,
            supports_selector_map=False,
        )

    def _raise(self) -> None:
        raise BrowserCapabilityError(
            "backend_not_configured",
            "BrowserUseAdapter: интеграция browser-use не подключена в этом билде",
        )

    async def start(self, req: BrowserAcquireRequest) -> BrowserAcquireResult:
        _ = req
        self._raise()
        raise AssertionError("unreachable")

    async def navigate(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult:
        _ = page, req
        self._raise()
        raise AssertionError("unreachable")

    async def run_action(self, page: BrowserPage, code: str, *, timeout_ms: int) -> JsonObject:
        _ = page, code, timeout_ms
        self._raise()
        raise AssertionError("unreachable")

    async def stop(self, page: BrowserPage) -> None:
        _ = page


class AgentBrowserAdapter:
    """
    Заглушка backend-а agent-browser.

    Связи:
    - Используется factory при `control_backend="agent_browser"`.

    Инварианты:
    - Любая активная операция (кроме `stop`) завершается `BrowserCapabilityError`.

    Мотивация:
    - Сохранить контракт API неизменным до готовности реальной интеграции.

    Переиспользование:
    - Стоит: временно в окружениях, где backend явно выключен.
    - Не стоит: как рабочий backend.
    """
    def features(self) -> BrowserControlFeatures:
        return BrowserControlFeatures(
            supports_js_injection_dom_tree=False,
            supports_cdp_dom_snapshot=False,
            supports_cdp_event_listeners=False,
            supports_ax_tree=False,
            supports_selector_map=False,
        )

    def _raise(self) -> None:
        raise BrowserCapabilityError(
            "backend_not_configured",
            "AgentBrowserAdapter: интеграция agent-browser не подключена в этом билде",
        )

    async def start(self, req: BrowserAcquireRequest) -> BrowserAcquireResult:
        _ = req
        self._raise()
        raise AssertionError("unreachable")

    async def navigate(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult:
        _ = page, req
        self._raise()
        raise AssertionError("unreachable")

    async def run_action(self, page: BrowserPage, code: str, *, timeout_ms: int) -> JsonObject:
        _ = page, code, timeout_ms
        self._raise()
        raise AssertionError("unreachable")

    async def stop(self, page: BrowserPage) -> None:
        _ = page
