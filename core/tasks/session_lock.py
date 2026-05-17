"""
Session Lock Middleware для TaskIQ.

Обеспечивает последовательное выполнение задач в рамках одной сессии (FIFO per session).
Использует Redis SETNX для атомарного захвата lock на session_id.

Алгоритм:
1. Перед выполнением задачи - пытаемся взять lock `session_lock:{session_id}`
2. Если lock занят - ждем его освобождения (polling с экспоненциальной задержкой)
3. После успешного выполнения - освобождаем lock
4. При ошибке - также освобождаем lock (чтобы не блокировать сессию навсегда)

Это гарантирует что задачи одной сессии выполняются строго последовательно,
даже если запущено несколько воркеров.
"""

import asyncio
from typing import Any

from taskiq import TaskiqMessage, TaskiqMiddleware, TaskiqResult

from core.config import get_settings
from core.logging import get_logger

try:
    import redis.asyncio as redis_async
except ImportError:
    redis_async = None

_redis_available = redis_async is not None

logger = get_logger(__name__)

# Время жизни lock в секундах (защита от зависших воркеров)
LOCK_TTL_SECONDS = 300  # 5 минут

# Параметры ожидания lock
LOCK_WAIT_INITIAL_MS = 50  # Начальная задержка
LOCK_WAIT_MAX_MS = 2000  # Максимальная задержка
LOCK_WAIT_TIMEOUT_SECONDS = 60  # Таймаут ожидания


class SessionLockMiddleware(TaskiqMiddleware):
    """
    Middleware для последовательного выполнения задач одной сессии.

    Работает только для задач с параметром session_id.
    Задачи без session_id выполняются параллельно без ограничений.
    """

    def __init__(self):
        super().__init__()
        self._redis_client = None
        self._locks_held: set[str] = set()

    async def _get_redis(self):
        """Получить Redis клиент (lazy initialization)"""
        if not _redis_available or redis_async is None:
            raise RuntimeError("redis не установлен")
        if self._redis_client is None:
            settings = get_settings()
            self._redis_client = redis_async.from_url(
                settings.database.redis_url,
                decode_responses=True,
            )
        return self._redis_client

    def _get_lock_key(self, session_id: str) -> str:
        """Ключ для lock в Redis"""
        return f"session_lock:{session_id}"

    async def _try_acquire_lock(self, session_id: str) -> bool:
        """Попытка взять lock на сессию (атомарно через SETNX)"""
        redis_client = await self._get_redis()
        lock_key = self._get_lock_key(session_id)

        # SETNX + expire атомарно
        acquired = await redis_client.set(
            lock_key,
            "locked",
            nx=True,  # SET если не существует
            ex=LOCK_TTL_SECONDS,  # TTL в секундах
        )

        if acquired:
            self._locks_held.add(session_id)
            logger.debug("session_lock.acquired", session_id=session_id)

        return bool(acquired)

    async def _wait_for_lock(self, session_id: str) -> bool:
        """
        Ожидание и захват lock с экспоненциальной задержкой.

        Returns:
            True если lock получен, False если таймаут
        """
        delay_ms = LOCK_WAIT_INITIAL_MS
        total_waited = 0.0

        while total_waited < LOCK_WAIT_TIMEOUT_SECONDS:
            if await self._try_acquire_lock(session_id):
                return True

            # Ждем с экспоненциальной задержкой
            await asyncio.sleep(delay_ms / 1000)
            total_waited += delay_ms / 1000
            delay_ms = min(delay_ms * 2, LOCK_WAIT_MAX_MS)

        logger.warning("session_lock.wait_timeout", session_id=session_id)
        return False

    async def _release_lock(self, session_id: str) -> None:
        """Освободить lock сессии"""
        if session_id not in self._locks_held:
            return

        redis_client = await self._get_redis()
        lock_key = self._get_lock_key(session_id)

        await redis_client.delete(lock_key)
        self._locks_held.discard(session_id)
        logger.debug("session_lock.released", session_id=session_id)

    def _extract_session_id(self, message: TaskiqMessage) -> str | None:
        """Извлечь session_id из аргументов задачи"""
        # Проверяем kwargs
        if "session_id" in message.kwargs:
            return message.kwargs["session_id"]

        # Проверяем args (session_id обычно второй аргумент после flow_id)
        # НО только если это строка! (не dict или другой тип)
        if len(message.args) >= 2 and isinstance(message.args[1], str):
            return message.args[1]

        return None

    async def pre_execute(self, message: TaskiqMessage) -> TaskiqMessage:
        """
        Вызывается перед выполнением задачи.

        Пытается взять lock на session_id.
        Если lock занят - ждет его освобождения.
        """
        session_id = self._extract_session_id(message)

        # Задачи без session_id выполняются без ограничений
        if not session_id:
            return message

        # Пытаемся взять lock (с ожиданием если занят)
        if await self._wait_for_lock(session_id):
            # Lock получен, сохраняем session_id для post_execute
            message.labels["_session_lock_id"] = session_id
        else:
            logger.error("session_lock.acquire_failed", session_id=session_id)

        return message

    async def post_execute(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
    ) -> None:
        """
        Вызывается после выполнения задачи.

        Освобождает lock.
        """
        session_id = message.labels.get("_session_lock_id")

        if not session_id:
            return

        # Освобождаем lock после выполнения
        await self._release_lock(session_id)

    async def on_error(
        self,
        message: TaskiqMessage,
        result: TaskiqResult[Any],
        exception: BaseException,
    ) -> None:
        """
        Вызывается при ошибке выполнения задачи.

        Освобождает lock чтобы не блокировать сессию.
        """
        session_id = message.labels.get("_session_lock_id")

        if session_id and session_id in self._locks_held:
            await self._release_lock(session_id)
            logger.warning("session_lock.released_after_error", session_id=session_id)


# Экземпляр middleware для добавления в брокер
session_lock_middleware = SessionLockMiddleware()
