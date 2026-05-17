"""
Механизм отмены выполнения flow.

CancellationToken проверяет Redis-ключ cancel:{task_id}.
Проверка rate-limited (не чаще раз в 0.5с) чтобы не нагружать Redis
при частых вызовах из LLM-стрима.

Токен доступен через ContextVar — не нужно менять сигнатуры.
"""

from __future__ import annotations

import time
from contextvars import ContextVar
from typing import TYPE_CHECKING

from apps.flows.config import get_settings
from core.clients.redis_client import RedisClient
from core.errors import FlowWallClockTimeoutError
from core.logging import get_logger

if TYPE_CHECKING:
    from core.state import ExecutionState

logger = get_logger(__name__)

CANCEL_KEY_TTL = 300


class FlowCancelled(Exception):
    """Flow был отменен пользователем."""

    def __init__(self, task_id: str):
        self.task_id = task_id
        super().__init__(f"Flow cancelled: task_id={task_id}")


class CancellationToken:
    """
    Проверяет Redis-ключ cancel:{task_id} с rate-limiting.

    Rate-limiting нужен потому что check вызывается из inner-loop LLM-стрима
    (после каждого SSE-чанка), и без лимита это десятки GET в секунду.
    """

    def __init__(
        self,
        task_id: str,
        redis_client: RedisClient,
        check_interval: float = 0.5,
    ):
        self.task_id = task_id
        self.redis = redis_client
        self._cancelled = False
        self._last_check_time = 0.0
        self._check_interval = check_interval

    async def is_cancelled(self) -> bool:
        if self._cancelled:
            return True
        now = time.monotonic()
        if now - self._last_check_time < self._check_interval:
            return False
        self._last_check_time = now
        value = await self.redis.get(f"cancel:{self.task_id}")
        if value is not None:
            self._cancelled = True
        return self._cancelled

    async def cancel(self) -> None:
        """Устанавливает ключ отмены в Redis."""
        await self.redis.set(f"cancel:{self.task_id}", "1", ttl=CANCEL_KEY_TTL)
        self._cancelled = True

    async def cleanup(self) -> None:
        """Удаляет ключ отмены из Redis."""
        await self.redis.delete(f"cancel:{self.task_id}")


_cancellation_token_var: ContextVar[CancellationToken | None] = ContextVar(
    "cancellation_token", default=None
)


def set_cancellation_token(token: CancellationToken | None) -> None:
    _cancellation_token_var.set(token)


def get_cancellation_token() -> CancellationToken | None:
    return _cancellation_token_var.get()


async def check_cancellation(state: ExecutionState | None = None) -> None:
    """
    Проверяет: wall-clock дедлайн run flow, затем отмена по Redis.

    Вызывается из _execute_loop, _react_loop и _call_llm.
    Бросает FlowWallClockTimeoutError или FlowCancelled.
    Если токен не установлен — отмена по Redis не проверяется.
    """
    if state is not None and state.flow_deadline_monotonic is not None:
        if time.monotonic() >= state.flow_deadline_monotonic:
            ts = state.flow_timeout_effective_seconds
            if ts is None:
                ts = get_settings().default_flow_timeout_seconds
            raise FlowWallClockTimeoutError(
                flow_id=state.session_flow_id,
                timeout_seconds=int(ts),
            )
    token = get_cancellation_token()
    if token is None:
        return
    if await token.is_cancelled():
        raise FlowCancelled(token.task_id)
