"""
Протокол BrowserControlAdapter (§17.3).
"""

from __future__ import annotations

from typing import Protocol

from apps.browser.contracts.control_types import BrowserControlFeatures
from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserPage,
)
from core.types import JsonObject


class BrowserControlAdapter(Protocol):
    """
    Единый внешний контракт control-операций браузера.

    Связи:
    - Реализации выбираются factory (`PlaywrightAdapter`, `BrowserUseAdapter`, `AgentBrowserAdapter`).
    - HTTP API работает только через этот контракт.

    Инварианты:
    - Набор методов и форма ответов должны оставаться стабильными независимо от backend-а.

    Мотивация:
    - API и orchestration не должны зависеть от конкретной реализации backend-а.

    Переиспользование:
    - Стоит: как обязательный контракт для любых новых control-адаптеров.
    """
    async def start(self, req: BrowserAcquireRequest) -> BrowserAcquireResult: ...

    async def navigate(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult: ...

    async def run_action(self, page: BrowserPage, code: str, *, timeout_ms: int) -> JsonObject: ...

    async def stop(self, page: BrowserPage) -> None: ...

    def features(self) -> BrowserControlFeatures: ...
