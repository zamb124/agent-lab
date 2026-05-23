"""Протоколы Browser Runtime (§17)."""

from __future__ import annotations

from typing import Protocol

from apps.browser.engine.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserContextHandle,
    BrowserFetchRequest,
    BrowserFetchResult,
    BrowserPage,
)


class BrowserInteractor(Protocol):
    """
    Контракт исполняющего браузерного слоя.

    Мотивация:
    - Зафиксировать стабильный API между orchestration/control-слоем и конкретной реализацией.
    - Разрешить замену движка без переписывания HTTP API.

    Связи:
    - Реализация (`PlaywrightBrowserInteractor`) используется control adapter-ом.

    Инварианты:
    - API acquire/fetch/save/restore/release должно оставаться стабильным для orchestration-слоя.

    Переиспользование:
    - Стоит: как обязательный интерфейс для любых новых backend-реализаций interactor.
    """
    async def acquire(self, req: BrowserAcquireRequest) -> BrowserAcquireResult: ...

    async def fetch(self, page: BrowserPage, req: BrowserFetchRequest) -> BrowserFetchResult: ...

    async def save_state(self, context: BrowserContextHandle, shared_storage_key: str) -> str: ...

    async def restore_state(self, context: BrowserContextHandle, state_key: str) -> None: ...

    async def release(self, page: BrowserPage) -> None: ...
