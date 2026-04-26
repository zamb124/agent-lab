"""
Протоколы Browser Runtime (§17, §30.5).
"""

from __future__ import annotations

from typing import Any, Protocol

from apps.browser.runtime.types import (
    BrowserAcquireRequest,
    BrowserAcquireResult,
    BrowserFetchRequest,
    BrowserFetchResult,
    ExecCodeResult,
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
    - API acquire/fetch/exec/save/restore/release должно оставаться стабильным для orchestration-слоя.

    Переиспользование:
    - Стоит: как обязательный интерфейс для любых новых backend-реализаций interactor.
    """
    async def acquire(self, req: BrowserAcquireRequest) -> BrowserAcquireResult: ...

    async def fetch(self, page: Any, req: BrowserFetchRequest) -> BrowserFetchResult: ...

    async def exec_code(self, page: Any, code: str, *, timeout_ms: int) -> ExecCodeResult: ...

    async def save_state(self, context: Any, shared_storage_key: str) -> str: ...

    async def restore_state(self, context: Any, state_key: str) -> None: ...

    async def release(self, page: Any) -> None: ...


class CDPLifecycleManager(Protocol):
    """
    Контракт lifecycle-операций над CDP endpoint-ами и сессиями.

    Мотивация:
    - Вынести операции обслуживания из бизнес-логики interactor/API.

    Связи:
    - Реализуется `CDPLifecycleManagerImpl` и вызывается фасадом/runtime-операциями обслуживания.

    Инварианты:
    - Операции должны быть безопасны при повторном вызове и не нарушать консистентность lease-учёта.

    Переиспользование:
    - Стоит: как общий интерфейс для альтернативных lifecycle-реализаций.
    """
    async def drain(self, endpoint_key: str, timeout_sec: int) -> bool: ...

    async def kill_session(self, session_id: str) -> None: ...

    async def disconnect(self, endpoint_key: str) -> None: ...

    async def terminate_browser(self, endpoint_key: str) -> None: ...
