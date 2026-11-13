"""Session lock для TaskIQ задач.

Обеспечивает взаимное исключение (не строгий FIFO) задач одного session_id:
тело задачи ждёт освобождения lock до таймаута и падает ошибкой, если lock
занят дольше — никогда не исполняется без захвата. Lock — Redis SETNX с
токеном владельца и TTL; release — Lua compare-and-delete, чтобы истёкший
по TTL lock не снимался новым владельцем.

Захват — внутри границы задачи (``wrap_with_session_lock`` применяется
``@platform_task`` к функциям с параметром ``session_id``), а не в
middleware: таймаут ожидания становится обычной ошибкой задачи и проходит
конвейер результата (on_error, retry по spec, ack). Исключение из
``pre_execute`` middleware обходило бы конвейер результата TaskIQ.

Это мьютекс для гонок одной сессии, а не бизнес-сериализация: строгая
очередь команд в леджере — `core/lanes` (database.mdc § Полосы).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import ParamSpec, TypeVar

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_TASK_LOCK_ACQUIRED,
    LOG_SESSION_ID,
    LOG_TASK_LOCK_WAIT_MS,
)

logger = get_logger(__name__)

# Время жизни lock в секундах (защита от зависших воркеров)
LOCK_TTL_SECONDS = 300  # 5 минут

# Параметры ожидания lock
LOCK_WAIT_INITIAL_MS = 50  # Начальная задержка
LOCK_WAIT_MAX_MS = 2000  # Максимальная задержка
LOCK_WAIT_TIMEOUT_SECONDS = 60  # Таймаут ожидания

_RELEASE_IF_OWNER = (
    "if redis.call('GET', KEYS[1]) == ARGV[1] then "
    "return redis.call('DEL', KEYS[1]) else return 0 end"
)

_FuncParams = ParamSpec("_FuncParams")
_FuncReturn = TypeVar("_FuncReturn")


class SessionLockTimeoutError(RuntimeError):
    """Lock сессии не получен за таймаут ожидания; задача уходит на retry/fail."""

    def __init__(self, session_id: str, timeout_seconds: float) -> None:
        super().__init__(
            f"session_lock timeout: session {session_id} waited {timeout_seconds}s"
        )
        self.session_id: str = session_id


_redis_client: RedisClient | None = None


async def _redis() -> RedisClient:
    """Redis для session-lock: один lazy-клиент на процесс воркера."""
    global _redis_client
    if _redis_client is None:
        client = RedisClient(get_settings().database.redis_url)
        await client.connect()
        _redis_client = client
    return _redis_client


def _lock_key(session_id: str) -> str:
    return f"session_lock:{session_id}"


async def _try_acquire_lock(session_id: str, token: str) -> bool:
    redis_client = await _redis()
    acquired = await redis_client.set_nx(
        _lock_key(session_id), token, LOCK_TTL_SECONDS
    )
    if acquired:
        logger.debug("session_lock.acquired", session_id=session_id)
    return acquired


async def _wait_for_lock(session_id: str, token: str) -> None:
    """Ждать и захватить lock; при таймауте — SessionLockTimeoutError."""
    delay_ms = LOCK_WAIT_INITIAL_MS
    total_waited = 0.0

    while total_waited < LOCK_WAIT_TIMEOUT_SECONDS:
        if await _try_acquire_lock(session_id, token):
            return

        # Ждем с экспоненциальной задержкой
        await asyncio.sleep(delay_ms / 1000)
        total_waited += delay_ms / 1000
        delay_ms = min(delay_ms * 2, LOCK_WAIT_MAX_MS)

    logger.error("session_lock.acquire_failed", session_id=session_id)
    raise SessionLockTimeoutError(session_id, LOCK_WAIT_TIMEOUT_SECONDS)


async def _release_lock(session_id: str, token: str) -> None:
    """Освободить lock сессии, если владелец — этот токен."""
    redis_client = await _redis()
    released = await redis_client.eval(
        _RELEASE_IF_OWNER, 1, _lock_key(session_id), token
    )
    if released != 1:
        logger.warning(
            "session_lock.release_not_owner",
            session_id=session_id,
            reason="lock expired or reacquired by another worker",
        )
    else:
        logger.debug("session_lock.released", session_id=session_id)


@asynccontextmanager
async def session_lock(session_id: str) -> AsyncGenerator[None]:
    """Держать session-lock на время исполнения тела задачи."""
    token = uuid.uuid4().hex
    lock_wait_start = time.perf_counter()
    await _wait_for_lock(session_id, token)
    lock_wait_ms = round((time.perf_counter() - lock_wait_start) * 1000.0, 3)
    # task_id/task_name/task_queue подставляет скоуп LoggingMiddleware.
    logger.info(
        EVENT_TASK_LOCK_ACQUIRED,
        **{
            LOG_SESSION_ID: session_id,
            LOG_TASK_LOCK_WAIT_MS: lock_wait_ms,
        },
    )
    try:
        yield
    finally:
        await _release_lock(session_id, token)


def wrap_with_session_lock(
    func: Callable[_FuncParams, Awaitable[_FuncReturn]],
) -> Callable[_FuncParams, Awaitable[_FuncReturn]]:
    """Обёртка тела задачи session-lock для функций с параметром session_id.

    Задачи без ``session_id`` в сигнатуре возвращаются без обёртки — lock
    применяется только там, где сессия объявлена контрактом функции.
    """
    signature = inspect.signature(func)
    if "session_id" not in signature.parameters:
        return func

    @functools.wraps(func)
    async def _locked(
        *args: _FuncParams.args, **kwargs: _FuncParams.kwargs
    ) -> _FuncReturn:
        bound = signature.bind(*args, **kwargs)
        session_id = bound.arguments.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return await func(*args, **kwargs)
        async with session_lock(session_id):
            return await func(*args, **kwargs)

    return _locked
