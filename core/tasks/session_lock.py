"""
Session Lock Middleware для TaskIQ.

Обеспечивает взаимное исключение (не строгий FIFO) задач одного session_id:
задача ждёт освобождения lock до таймаута и падает ошибкой, если lock занят
дольше — никогда не исполняется без захвата. Lock — Redis SETNX с токеном
владельца и TTL; release — Lua compare-and-delete, чтобы истёкший по TTL lock
не снимался новым владельцем.

Это мьютекс для гонок одной сессии, а не бизнес-сериализация: строгая очередь
команд в леджере — `core/lanes` (database.mdc § Полосы).

Алгоритм:
1. Перед выполнением задачи - пытаемся взять lock `session_lock:{session_id}`
2. Если lock занят - ждем его освобождения (polling с экспоненциальной задержкой)
3. После успешного выполнения - освобождаем lock по токену
4. При ошибке - также освобождаем lock (чтобы не блокировать сессию навсегда)
"""

import asyncio
import time
import uuid
from typing import override

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from core.clients.redis_client import RedisClient
from core.config import get_settings
from core.logging import get_logger
from core.logging.attributes import (
    EVENT_TASK_LOCK_ACQUIRED,
    LOG_SESSION_ID,
    LOG_TASK_ID,
    LOG_TASK_LOCK_WAIT_MS,
    LOG_TASK_NAME,
    LOG_TASK_QUEUE,
)
from core.tasks.message_contract import (
    set_task_message_string_label,
    task_message_string_arg,
    task_message_string_kwarg,
    task_message_string_label,
)
from core.types import JsonValue

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


class SessionLockTimeoutError(RuntimeError):
    """Lock сессии не получен за таймаут ожидания; задача уходит на retry/fail."""

    def __init__(self, session_id: str, timeout_seconds: float) -> None:
        super().__init__(
            f"session_lock timeout: session {session_id} waited {timeout_seconds}s"
        )
        self.session_id: str = session_id


class SessionLockMiddleware(TaskiqMiddleware):
    """
    Middleware для взаимного исключения задач одной сессии.

    Работает только для задач с параметром session_id.
    Задачи без session_id выполняются параллельно без ограничений.
    Экземпляр создаётся на брокер (queue_name в конструкторе).
    """

    def __init__(self, queue_name: str) -> None:
        super().__init__()
        if not queue_name.strip():
            raise ValueError('SessionLockMiddleware: queue_name is required')
        self._queue_name: str = queue_name
        self._redis_client: RedisClient | None = None
        self._locks_held: dict[str, str] = {}

    async def _get_redis(self) -> RedisClient:
        """Получить Redis клиент (lazy initialization)"""
        if self._redis_client is None:
            settings = get_settings()
            client = RedisClient(settings.database.redis_url)
            await client.connect()
            self._redis_client = client
        return self._redis_client

    def _get_lock_key(self, session_id: str) -> str:
        """Ключ для lock в Redis"""
        return f"session_lock:{session_id}"

    async def _try_acquire_lock(self, session_id: str) -> bool:
        """Попытка взять lock на сессию (атомарно через SETNX с токеном)"""
        redis_client = await self._get_redis()
        lock_key = self._get_lock_key(session_id)
        token = uuid.uuid4().hex

        acquired = await redis_client.set_nx(lock_key, token, LOCK_TTL_SECONDS)

        if acquired:
            self._locks_held[session_id] = token
            logger.debug("session_lock.acquired", session_id=session_id)

        return acquired

    async def _wait_for_lock(self, session_id: str) -> None:
        """Ждать и захватить lock; при таймауте — SessionLockTimeoutError."""
        delay_ms = LOCK_WAIT_INITIAL_MS
        total_waited = 0.0

        while total_waited < LOCK_WAIT_TIMEOUT_SECONDS:
            if await self._try_acquire_lock(session_id):
                return

            # Ждем с экспоненциальной задержкой
            await asyncio.sleep(delay_ms / 1000)
            total_waited += delay_ms / 1000
            delay_ms = min(delay_ms * 2, LOCK_WAIT_MAX_MS)

        logger.error("session_lock.acquire_failed", session_id=session_id)
        raise SessionLockTimeoutError(session_id, LOCK_WAIT_TIMEOUT_SECONDS)

    async def _release_lock(self, session_id: str) -> None:
        """Освободить lock сессии, если владелец — этот токен."""
        token = self._locks_held.pop(session_id, None)
        if token is None:
            return

        redis_client = await self._get_redis()
        lock_key = self._get_lock_key(session_id)

        released = await redis_client.eval(_RELEASE_IF_OWNER, 1, lock_key, token)
        if released != 1:
            logger.warning(
                "session_lock.release_not_owner",
                session_id=session_id,
                reason="lock expired or reacquired by another worker",
            )
        else:
            logger.debug("session_lock.released", session_id=session_id)

    def _extract_session_id(self, message: TaskiqMessage) -> str | None:
        """Извлечь session_id из аргументов задачи"""
        # Проверяем kwargs
        session_id = task_message_string_kwarg(message, "session_id")
        if session_id is not None:
            return session_id

        positional_session_id = task_message_string_arg(message, 1)
        if positional_session_id is not None:
            return positional_session_id

        return None

    @override
    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """
        Вызывается перед выполнением задачи.

        Пытается взять lock на session_id. Если lock занят дольше таймаута —
        SessionLockTimeoutError, задача не исполняется без lock.
        """
        session_id = self._extract_session_id(message)

        # Задачи без session_id выполняются без ограничений
        if not session_id:
            return message

        lock_wait_start = time.perf_counter()
        await self._wait_for_lock(session_id)
        lock_wait_ms = round((time.perf_counter() - lock_wait_start) * 1000.0, 3)
        # Lock получен, сохраняем session_id для post_execute
        set_task_message_string_label(message, "_session_lock_id", session_id)
        set_task_message_string_label(message, "_session_lock_wait_ms", str(lock_wait_ms))
        logger.info(
            EVENT_TASK_LOCK_ACQUIRED,
            **{
                LOG_TASK_ID: message.task_id,
                LOG_TASK_NAME: message.task_name,
                LOG_TASK_QUEUE: self._queue_name,
                LOG_TASK_LOCK_WAIT_MS: lock_wait_ms,
                LOG_SESSION_ID: session_id,
            },
        )

        return message

    @override
    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[JsonValue],
    ) -> None:
        """
        Вызывается после выполнения задачи.

        Освобождает lock.
        """
        _ = result
        session_id = task_message_string_label(message, "_session_lock_id")

        if not session_id:
            return

        # Освобождаем lock после выполнения
        await self._release_lock(session_id)

    @override
    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[JsonValue],
        exception: BaseException,
    ) -> None:
        """
        Вызывается при ошибке выполнения задачи.

        Освобождает lock чтобы не блокировать сессию.
        """
        _ = result
        _ = exception
        session_id = task_message_string_label(message, "_session_lock_id")

        if session_id and session_id in self._locks_held:
            await self._release_lock(session_id)
            logger.warning("session_lock.released_after_error", session_id=session_id)
