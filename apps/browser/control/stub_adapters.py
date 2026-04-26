"""
Заглушки BrowserUse / AgentBrowser: контракт без реального backend (Модуль 02).
"""

from __future__ import annotations

from typing import Any

from apps.browser.control.types import BrowserCapabilityError, BrowserControlFeatures
from apps.browser.runtime.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
)


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

    async def navigate(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult:
        _ = page, req
        self._raise()
        raise AssertionError("unreachable")

    async def run_action(self, page: Any, code: str, *, timeout_ms: int) -> dict[str, Any]:
        _ = page, code, timeout_ms
        self._raise()
        raise AssertionError("unreachable")

    async def get_visibility_tree(
        self,
        page: Any,
        *,
        budget: int,
        emit_generic_role: bool,
    ) -> dict[str, Any]:
        _ = page, budget, emit_generic_role
        self._raise()
        raise AssertionError("unreachable")

    async def get_accessibility_tree(self, page: Any, *, emit_generic_role: bool) -> dict[str, Any]:
        _ = page, emit_generic_role
        self._raise()
        raise AssertionError("unreachable")

    async def get_dom_event_listeners(self, page: Any) -> dict[str, Any]:
        _ = page
        self._raise()
        raise AssertionError("unreachable")

    async def stop(self, page: Any) -> None:
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

    async def navigate(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult:
        _ = page, req
        self._raise()
        raise AssertionError("unreachable")

    async def run_action(self, page: Any, code: str, *, timeout_ms: int) -> dict[str, Any]:
        _ = page, code, timeout_ms
        self._raise()
        raise AssertionError("unreachable")

    async def get_visibility_tree(
        self,
        page: Any,
        *,
        budget: int,
        emit_generic_role: bool,
    ) -> dict[str, Any]:
        _ = page, budget, emit_generic_role
        self._raise()
        raise AssertionError("unreachable")

    async def get_accessibility_tree(self, page: Any, *, emit_generic_role: bool) -> dict[str, Any]:
        _ = page, emit_generic_role
        self._raise()
        raise AssertionError("unreachable")

    async def get_dom_event_listeners(self, page: Any) -> dict[str, Any]:
        _ = page
        self._raise()
        raise AssertionError("unreachable")

    async def stop(self, page: Any) -> None:
        _ = page
