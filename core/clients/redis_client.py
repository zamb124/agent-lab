"""
Redis клиент для кэширования, сессий и Pub/Sub streaming.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Protocol, TypedDict
from typing import cast as type_cast
from urllib.parse import urlparse

from redis.asyncio.client import PubSub, Redis
from redis.exceptions import RedisError

from core.logging import get_logger
from core.types import JsonValue, require_json_value

logger = get_logger(__name__)


class RedisOperationError(RuntimeError):
    """Атомарная Redis-операция не удалась после retry.

    Тихий fallback `return None/False/0` для атомарных команд (set_nx, eval,
    delete) ломает consistency: caller, не зная об ошибке, считает что лок
    взят / событие отправлено / запись удалена. Все атомарные методы
    `RedisClient` поднимают это исключение вместо тихого `return False`.
    """


class _RedisSetCommand(Protocol):
    def __call__(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> Awaitable[bool | None]: ...


class _RedisGetMessageCommand(Protocol):
    def __call__(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> Awaitable["_RedisPubSubMessage | None"]: ...


class _RedisPubSubMessage(TypedDict):
    type: str
    data: str


class _RedisSdkPubSub:
    def __init__(self, raw: PubSub) -> None:
        self._raw: PubSub = raw

    async def subscribe(self, *channels: str) -> None:
        command = type_cast(Callable[..., Awaitable[None]], self._raw.subscribe)
        await command(*channels)

    async def unsubscribe(self, *channels: str) -> None:
        command = type_cast(Callable[..., Awaitable[None]], self._raw.unsubscribe)
        await command(*channels)

    async def aclose(self) -> None:
        command = type_cast(Callable[[], Awaitable[None]], self._raw.aclose)
        await command()

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> _RedisPubSubMessage | None:
        command = type_cast(_RedisGetMessageCommand, self._raw.get_message)
        return await command(ignore_subscribe_messages=ignore_subscribe_messages, timeout=timeout)


class _RedisSdkConnection:
    def __init__(self, raw: Redis) -> None:
        self._raw: Redis = raw

    async def ping(self) -> bool:
        command = type_cast(Callable[[], Awaitable[bool]], self._raw.ping)
        return await command()

    async def aclose(self) -> None:
        command = type_cast(Callable[[], Awaitable[None]], self._raw.aclose)
        await command()

    async def get(self, key: str) -> str | None:
        command = type_cast(Callable[[str], Awaitable[str | None]], self._raw.get)
        return await command(key)

    async def getdel(self, key: str) -> str | None:
        command = type_cast(Callable[[str], Awaitable[str | None]], self._raw.getdel)
        return await command(key)

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool | None:
        command = type_cast(_RedisSetCommand, self._raw.set)
        return await command(key, value, ex=ex, nx=nx)

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        command = type_cast(Callable[[str, int, str], Awaitable[bool]], self._raw.setex)
        return await command(key, seconds, value)

    async def delete(self, *keys: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.delete)
        return await command(*keys)

    async def eval(self, script: str, numkeys: int, *keys_and_args: JsonValue) -> JsonValue:
        command = type_cast(Callable[..., Awaitable[JsonValue]], self._raw.eval)
        return await command(script, numkeys, *keys_and_args)

    async def rpush(self, key: str, *values: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.rpush)
        return await command(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        command = type_cast(Callable[[str, int, int], Awaitable[list[str]]], self._raw.lrange)
        return await command(key, start, end)

    async def publish(self, channel: str, message: str) -> int:
        command = type_cast(Callable[[str, str], Awaitable[int]], self._raw.publish)
        return await command(channel, message)

    def pubsub(self) -> _RedisSdkPubSub:
        command = type_cast(Callable[[], PubSub], self._raw.pubsub)
        return _RedisSdkPubSub(command())


class RedisClient:
    """
    Redis клиент для кэширования токенов и сессий с auto-reconnect.
    """

    def __init__(self, redis_url: str, max_retries: int = 3):
        """
        Args:
            redis_url: URL подключения к Redis (например, redis://localhost:6379/0)
            max_retries: Максимальное количество попыток переподключения
        """
        self.redis_url: str = redis_url
        self._client: _RedisSdkConnection | None = None
        self._max_retries: int = max_retries
        self._connection_lock: asyncio.Lock = asyncio.Lock()

    async def connect(self) -> None:
        """Подключается к Redis"""
        try:
            parsed = urlparse(self.redis_url)
            db = int(parsed.path.lstrip("/")) if parsed.path else 0

            self._client = _RedisSdkConnection(
                Redis(
                    host=parsed.hostname or "localhost",
                    port=parsed.port or 6379,
                    db=db,
                    decode_responses=True,
                    socket_connect_timeout=5,
                    socket_timeout=5,
                    health_check_interval=30,
                )
            )
            _ = await self._client.ping()
            logger.info("RedisClient: подключение к Redis установлено")
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.warning(f"RedisClient: не удалось подключиться к Redis: {e}")
            self._client = None

    async def close(self) -> None:
        """Закрывает соединение с Redis"""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("RedisClient: соединение закрыто")

    async def _ensure_connected(self) -> bool:
        """Автоматическое переподключение с retry и exponential backoff"""
        async with self._connection_lock:
            if self._client:
                try:
                    _ = await self._client.ping()
                    return True
                except (RedisError, OSError, asyncio.TimeoutError):
                    logger.warning("Redis connection lost, reconnecting...")
                    self._client = None

            for attempt in range(self._max_retries):
                try:
                    await self.connect()
                    if self._client:
                        logger.info("Redis reconnected successfully")
                        return True
                except (RedisError, OSError, asyncio.TimeoutError) as e:
                    if attempt < self._max_retries - 1:
                        wait_time: int = 1 << attempt
                        logger.warning(
                            f"Reconnect attempt {attempt + 1} failed: {e}, retry in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to reconnect to Redis after {self._max_retries} attempts"
                        )

            return False

    def _require_client(self) -> _RedisSdkConnection:
        if self._client is None:
            raise RuntimeError("Redis client not connected after retries")
        return self._client

    async def get(self, key: str) -> str | None:
        """
        Read-path: возвращает `None` если ключ отсутствует ИЛИ Redis недоступен.

        Это сознательный fallback для cache-read сценариев. Caller, который
        не может пережить недоступность Redis (lock NX, ledger), использует
        отдельные атомарные методы (`set_nx`, `eval`, `delete`), которые
        поднимают `RedisOperationError`.
        """
        if not await self._ensure_connected():
            return None
        client = self._require_client()

        try:
            return await client.get(key)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.error(f"Get failed for key {key}: {e}")
            if await self._ensure_connected():
                try:
                    client = self._require_client()
                    return await client.get(key)
                except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                    logger.error(f"Get retry failed for key {key}: {retry_error}")
            return None

    async def getdel(self, key: str) -> str | None:
        """
        Атомарно вернуть и удалить ключ.

        Если Redis недоступен после retry — поднимает `RedisOperationError`,
        потому что caller (one-shot токен, in-flight handoff) не может
        перепутать "ключа не было" и "не смогли достучаться до Redis".
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"getdel({key}): Redis недоступен после retry")
        client = self._require_client()
        try:
            return await client.getdel(key)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            logger.error(f"getdel failed for key {key}: {primary_error}")

        lua = "local v = redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]) end; return v"
        if not await self._ensure_connected():
            raise RedisOperationError(f"getdel({key}) lua: Redis недоступен после retry")
        try:
            client = self._require_client()
            lua_result = await client.eval(lua, 1, key)
        except (RedisError, OSError, asyncio.TimeoutError) as lua_error:
            raise RedisOperationError(f"getdel({key}) lua: {lua_error}") from lua_error
        if lua_result is None or isinstance(lua_result, str):
            return lua_result
        raise RedisOperationError(f"getdel({key}) lua вернул non-string: {type(lua_result).__name__}")

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Устанавливает значение по ключу с auto-reconnect; True при успехе."""
        if not await self._ensure_connected():
            return False

        for attempt in range(2):
            try:
                client = self._require_client()
                _ = await client.set(key, value, ex=ttl)
                return True
            except (RedisError, OSError, asyncio.TimeoutError) as e:
                if attempt == 0 and await self._ensure_connected():
                    continue
                logger.error(f"Set failed for key {key}: {e}")
                return False
        return False

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        """
        `SET key value NX EX ttl`. True только если ключ раньше отсутствовал.

        Атомарная команда: при Redis-ошибке поднимает `RedisOperationError`.
        Caller (distributed lock, idempotency guard, dedupe) не может
        интерпретировать "Redis недоступен" как "лок взят/не взят" — это
        прямой путь к double-execution.
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"set_nx({key}): Redis недоступен после retry")
        try:
            client = self._require_client()
            ok = await client.set(key, value, nx=True, ex=ttl_seconds)
            return bool(ok)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            logger.error(f"set_nx failed for key {key}: {primary_error}")
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"set_nx({key}): Redis недоступен после retry"
                ) from primary_error
            try:
                client = self._require_client()
                ok = await client.set(key, value, nx=True, ex=ttl_seconds)
                return bool(ok)
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(
                    f"set_nx({key}): {retry_error}"
                ) from retry_error

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Устанавливает значение с TTL."""
        if not await self._ensure_connected():
            return False
        try:
            client = self._require_client()
            _ = await client.setex(key, seconds, value)
            return True
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.error(f"RedisClient: ошибка установки ключа {key} с TTL: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """
        Удаляет ключи.

        Атомарная команда: при Redis-ошибке поднимает `RedisOperationError`.
        Тихий `return 0` маскирует "не смогли удалить" под "ключей не было".
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"delete({keys}): Redis недоступен после retry")
        try:
            client = self._require_client()
            return await client.delete(*keys)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            raise RedisOperationError(f"delete({keys}): {e}") from e

    async def eval(self, script: str, numkeys: int, *keys_and_args: JsonValue) -> JsonValue:
        """Выполняет Lua-скрипт (атомарные read-modify-write на стороне Redis)."""
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected after retries")
        client = self._require_client()
        return require_json_value(await client.eval(script, numkeys, *keys_and_args), "redis.eval")

    async def rpush(self, key: str, *values: str) -> int:
        """
        Добавляет значения в конец списка (RPUSH).

        Write-операция в ledger — поднимает `RedisOperationError`, чтобы
        caller не считал что событие записано когда Redis не достучали.
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"rpush({key}): Redis недоступен после retry")
        try:
            client = self._require_client()
            return await client.rpush(key, *values)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            raise RedisOperationError(f"rpush({key}): {e}") from e

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка (LRANGE), включая обе границы."""
        if not await self._ensure_connected():
            return []
        try:
            client = self._require_client()
            return await client.lrange(key, start, end)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.error(f"RedisClient: ошибка LRANGE из {key}: {e}")
            return []

    async def ping(self) -> bool:
        """Проверяет соединение с Redis."""
        if not self._client:
            return False
        try:
            _ = await self._client.ping()
            return True
        except (RedisError, OSError, asyncio.TimeoutError):
            return False

    async def open_pubsub(self) -> "_RedisSdkPubSub":
        """
        Открывает pub/sub-канал для ручного управления подпиской.

        В отличие от ``subscribe()`` (async-generator с idle/max таймаутами,
        ориентированный на длинные стримы), этот метод возвращает чистый
        SDK-объект для коротких ожиданий — например, ожидание release-event
        под distributed lock. Вызывающий обязан вызвать ``unsubscribe`` и
        ``aclose`` сам (обычно в ``finally``).
        """
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected")
        client = self._require_client()
        return client.pubsub()

    async def publish(self, channel: str, message: str) -> int:
        """Публикует сообщение в канал Pub/Sub с auto-reconnect и retry"""
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected after retries")

        # Попытка публикации с одним retry
        for attempt in range(2):
            try:
                client = self._require_client()
                return await client.publish(channel, message)
            except Exception as e:
                if attempt == 0:
                    logger.warning(f"Publish failed, reconnecting: {e}")
                    if await self._ensure_connected():
                        continue
                logger.error(f"Publish failed after retry: {e}")
                raise
        raise RuntimeError("Redis publish retry loop exited without result")

    async def subscribe(
        self,
        channel: str,
        timeout: float = 300.0,
        max_timeout: float = 3600.0,
        ready_event: asyncio.Event | None = None,
    ) -> AsyncIterator[str]:
        """
        Подписывается на канал и yield'ит сообщения с auto-reconnect.

        Idle-timeout: сбрасывается при каждом полученном сообщении.
        Max-timeout: абсолютный предел жизни подписки (защита от утечек).

        Args:
            channel: Имя канала
            timeout: Idle-таймаут в секундах (сбрасывается при каждом сообщении)
            max_timeout: Абсолютный потолок жизни подписки
            ready_event: Event для сигнализации о готовности подписки

        Yields:
            Сообщения из канала
        """
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected")

        client = self._require_client()
        pubsub = client.pubsub()

        try:
            await pubsub.subscribe(channel)
            logger.debug(f"Subscribed to {channel}")

            if ready_event:
                ready_event.set()

            start_time = time.monotonic()
            last_activity = start_time

            while True:
                now = time.monotonic()
                if now - start_time >= max_timeout:
                    logger.warning(
                        "Subscription max-timeout on %s after %.1fs", channel, now - start_time
                    )
                    break
                if now - last_activity >= timeout:
                    logger.warning(
                        "Subscription idle-timeout on %s after %.1fs idle",
                        channel,
                        now - last_activity,
                    )
                    break

                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message["type"] == "message":
                        last_activity = time.monotonic()
                        yield message["data"]
                except (RedisError, OSError, asyncio.TimeoutError) as e:
                    logger.error(f"Error receiving message from {channel}: {e}")
                    if await self._ensure_connected():
                        try:
                            await pubsub.unsubscribe(channel)
                            await pubsub.aclose()
                            client = self._require_client()
                            pubsub = client.pubsub()
                            await pubsub.subscribe(channel)
                            logger.info(f"Resubscribed to {channel}")
                        except (RedisError, OSError, asyncio.TimeoutError) as resub_error:
                            logger.error(f"Failed to resubscribe to {channel}: {resub_error}")
                            break
                    else:
                        break
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except (RedisError, OSError, asyncio.TimeoutError):
                pass
