"""
Адаптер Playwright: делегирование BrowserInteractor и AX visibility с лимитом budget.
"""

from __future__ import annotations

from typing import Any

from apps.browser.contracts.control_types import BrowserControlFeatures
from apps.browser.contracts.runtime import BrowserInteractor
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    ExecCodeResult,
)


def _exec_result_to_dict(r: ExecCodeResult) -> dict[str, Any]:
    return {
        "ok": r.ok,
        "stdout": r.stdout,
        "console_events": r.console_events,
        "dom_diff_ref": r.dom_diff_ref,
        "error": r.error,
    }


class PlaywrightAdapter:
    """
    Рабочая реализация `BrowserControlAdapter` на базе `BrowserInteractor`.

    Связи:
    - Делегирует start/navigate/run_action/stop в interactor.
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
        self._interactor = interactor

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

    async def navigate(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult:
        return await self._interactor.fetch(page, req)

    async def run_action(self, page: Any, code: str, *, timeout_ms: int) -> dict[str, Any]:
        result = await self._interactor.exec_code(page, code, timeout_ms=timeout_ms)
        return _exec_result_to_dict(result)

    async def stop(self, page: Any) -> None:
        await self._interactor.release(page)
