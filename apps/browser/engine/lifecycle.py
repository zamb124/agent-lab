"""
Graceful drain, kill_session, disconnect CDP (§30.5).
"""

from __future__ import annotations

import asyncio
import time

from apps.browser.engine.cdp_pool import CDPConnectionPool
from apps.browser.engine.page_lease_manager import PageLeaseManager


class CDPLifecycleManagerImpl:
    """
    Реализация lifecycle-контракта для endpoint-level обслуживания runtime.

    Мотивация:
    - Нужны управляемые операции drain/disconnect без потери консистентности lease.
    - Обычного `browser.close()` недостаточно: сначала надо остановить выдачу новых lease
      и корректно закрыть контексты.

    Связи:
    - Использует `PageLeaseManager` для контроля активных аренд.
    - Использует `CDPConnectionPool` для управления подключением к browser endpoint.

    Состояние:
    - Хранит ссылки на runtime-компоненты, обслуживающие lifecycle.

    Инварианты:
    - `drain` временно блокирует новые lease только для заданного endpoint-а.
    - `disconnect/terminate_browser` закрывают контексты перед закрытием Browser подключения.

    Переиспользование:
    - Стоит: для graceful shutdown и оперативных действий (kill/disconnect) в проде.
    - Не стоит: в короткоживущем сценарии "создал и сразу закрыл" без конкуренции.
    """
    def __init__(
        self,
        pool: CDPConnectionPool,
        lease_manager: PageLeaseManager,
    ) -> None:
        self._pool = pool
        self._lease_manager = lease_manager

    async def drain(self, endpoint_key: str, timeout_sec: int) -> bool:
        if timeout_sec <= 0:
            raise ValueError("timeout_sec должен быть положительным")
        self._lease_manager.set_endpoint_drain(endpoint_key, True)
        deadline = time.monotonic() + timeout_sec
        try:
            while time.monotonic() < deadline:
                if self._lease_manager.active_lease_count_for_endpoint(endpoint_key) == 0:
                    await self._lease_manager.close_idle_contexts_for_endpoint(endpoint_key)
                    await self._pool.disconnect(endpoint_key)
                    return True
                await asyncio.sleep(0.05)
            return False
        finally:
            self._lease_manager.set_endpoint_drain(endpoint_key, False)

    async def kill_session(self, session_id: str) -> None:
        await self._lease_manager.kill_session(session_id, warm_idle_sec=0)

    async def disconnect(self, endpoint_key: str) -> None:
        await self._lease_manager.kill_endpoint(endpoint_key)
        await self._pool.disconnect(endpoint_key)

    async def terminate_browser(self, endpoint_key: str) -> None:
        await self.disconnect(endpoint_key)
