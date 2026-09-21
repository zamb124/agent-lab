"""
Redis клиент для кэширования, сессий и Pub/Sub streaming.
"""

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol, TypedDict
from typing import cast as type_cast
from urllib.parse import urlparse

from redis.asyncio.client import PubSub, Redis
from redis.exceptions import RedisError

from core.logging import get_logger
from core.types import JsonValue, require_json_value

logger = get_logger(__name__)


@dataclass(frozen=True)
class RedisMemoryInfo:
    used_memory_bytes: int
    used_memory_rss_bytes: int
    maxmemory_bytes: int | None


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


class _RedisPipeline(Protocol):
    def ttl(self, key: str) -> object: ...

    def get(self, key: str) -> object: ...

    def execute(self) -> Awaitable[list[object]]: ...


class _RedisPipelineFactory(Protocol):
    def __call__(self, *, transaction: bool) -> _RedisPipeline: ...


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

    async def exists(self, *keys: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.exists)
        return await command(*keys)

    async def scan_keys(self, match: str, *, count: int = 500) -> list[str]:
        scan_command = type_cast(
            Callable[..., Awaitable[tuple[int, list[str]]]],
            self._raw.scan,
        )
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await scan_command(cursor, match=match, count=count)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    async def scan_all_keys(self, *, count: int = 500) -> list[str]:
        scan_command = type_cast(
            Callable[..., Awaitable[tuple[int, list[str]]]],
            self._raw.scan,
        )
        cursor = 0
        keys: list[str] = []
        while True:
            cursor, batch = await scan_command(cursor, count=count)
            keys.extend(batch)
            if cursor == 0:
                break
        return keys

    async def dbsize(self) -> int:
        command = type_cast(Callable[[], Awaitable[int]], self._raw.dbsize)
        return await command()

    async def ttl(self, key: str) -> int:
        command = type_cast(Callable[[str], Awaitable[int]], self._raw.ttl)
        return await command(key)

    async def xlen(self, stream: str) -> int:
        command = type_cast(Callable[[str], Awaitable[int]], self._raw.xlen)
        return await command(stream)

    async def memory_usage(self, key: str) -> int | None:
        command = type_cast(Callable[[str], Awaitable[int | None]], self._raw.memory_usage)
        return await command(key)

    async def info_memory(self) -> RedisMemoryInfo:
        command = type_cast(
            Callable[..., Awaitable[dict[str, str | int | float]]],
            self._raw.info,
        )
        info_payload = await command(section="memory")
        used_memory = info_payload.get("used_memory")
        used_memory_rss = info_payload.get("used_memory_rss")
        maxmemory = info_payload.get("maxmemory")
        if not isinstance(used_memory, int):
            raise RedisOperationError("info memory: used_memory missing or not int")
        if not isinstance(used_memory_rss, int):
            raise RedisOperationError("info memory: used_memory_rss missing or not int")
        maxmemory_bytes: int | None
        if isinstance(maxmemory, int) and maxmemory > 0:
            maxmemory_bytes = maxmemory
        else:
            maxmemory_bytes = None
        return RedisMemoryInfo(
            used_memory_bytes=used_memory,
            used_memory_rss_bytes=used_memory_rss,
            maxmemory_bytes=maxmemory_bytes,
        )

    async def eval(self, script: str, numkeys: int, *keys_and_args: JsonValue) -> JsonValue:
        command = type_cast(Callable[..., Awaitable[JsonValue]], self._raw.eval)
        return await command(script, numkeys, *keys_and_args)

    async def rpush(self, key: str, *values: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.rpush)
        return await command(key, *values)

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        command = type_cast(Callable[[str, int, int], Awaitable[list[str]]], self._raw.lrange)
        return await command(key, start, end)

    async def sadd(self, key: str, *members: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.sadd)
        return await command(key, *members)

    async def srem(self, key: str, *members: str) -> int:
        command = type_cast(Callable[..., Awaitable[int]], self._raw.srem)
        return await command(key, *members)

    async def smembers(self, key: str) -> set[str]:
        command = type_cast(Callable[[str], Awaitable[set[str]]], self._raw.smembers)
        return await command(key)

    async def publish(self, channel: str, message: str) -> int:
        command = type_cast(Callable[[str, str], Awaitable[int]], self._raw.publish)
        return await command(channel, message)

    def pubsub(self) -> _RedisSdkPubSub:
        command = type_cast(Callable[[], PubSub], self._raw.pubsub)
        return _RedisSdkPubSub(command())

    def pipeline(self) -> _RedisPipeline:
        pipeline_factory = type_cast(_RedisPipelineFactory, self._raw.pipeline)
        return pipeline_factory(transaction=False)


class RedisClient:
    """
    Redis-клиент для кэширования токенов и сессий с auto-reconnect.
    """

    def __init__(self, redis_url: str, max_retries: int = 3):
        """
        Аргументы:
            redis_url: URL подключения к Redis (например, redis://localhost:6379/0)
            max_retries: Максимальное количество попыток переподключения
        """
        self.redis_url: str = redis_url
        self._client: _RedisSdkConnection | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None
        self._max_retries: int = max_retries
        self._connection_lock: asyncio.Lock = asyncio.Lock()
        self._connection_lock_loop: asyncio.AbstractEventLoop | None = None

    def _rebind_if_event_loop_changed(self) -> None:
        """Starlette TestClient / ASGI lifespan поднимает новый loop на каждый ``with``.

        Клиент и ``asyncio.Lock``, созданные на прошлом loop, дают
        ``Future attached to a different loop`` на PING/DELETE. Как
        ``events_redis_client``: дропаем соединение без await на чужом loop.
        """
        running = asyncio.get_running_loop()
        if (
            self._connection_lock_loop is not None
            and self._connection_lock_loop is not running
        ):
            self._connection_lock = asyncio.Lock()
            self._connection_lock_loop = running
        if self._connection_lock_loop is None:
            self._connection_lock_loop = running
        if self._client is None:
            return
        if self._client_loop is running:
            return
        logger.warning("clients.redisclient.event.loop.changed.dropping")
        self._client = None
        self._client_loop = None

    async def connect(self) -> None:
        """Подключается к Redis"""
        self._rebind_if_event_loop_changed()
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
            self._client_loop = asyncio.get_running_loop()
            logger.info("clients.redisclient.redis")
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.warning("redis.connect_failed", error=str(e))
            self._client = None
            self._client_loop = None

    async def close(self) -> None:
        """Закрывает соединение с Redis"""
        self._rebind_if_event_loop_changed()
        if self._client:
            await self._client.aclose()
            self._client = None
            self._client_loop = None
            logger.info("clients.redisclient")

    async def _ensure_connected(self) -> bool:
        """Автоматическое переподключение с retry и экспоненциальной задержкой"""
        self._rebind_if_event_loop_changed()
        async with self._connection_lock:
            if self._client:
                try:
                    _ = await self._client.ping()
                    return True
                except (RedisError, OSError, asyncio.TimeoutError):
                    logger.warning("clients.redis.connection.lost.reconnecting")
                    self._client = None

            for attempt in range(self._max_retries):
                try:
                    await self.connect()
                    if self._client:
                        logger.info("clients.redis.reconnected.successfully")
                        return True
                except (RedisError, OSError, asyncio.TimeoutError) as e:
                    if attempt < self._max_retries - 1:
                        wait_time: int = 1 << attempt
                        logger.warning(
                            "redis.reconnect_retry",
                            attempt=attempt + 1,
                            error=str(e),
                            retry_in_s=wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            "redis.reconnect_failed",
                            attempts=self._max_retries,
                        )

            return False

    def _require_client(self) -> _RedisSdkConnection:
        if self._client is None:
            raise RuntimeError("Redis client not connected after retries")
        return self._client

    async def get(self, key: str) -> str | None:
        """
        Путь чтения: возвращает ``None``, если ключ отсутствует или Redis недоступен.

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
            logger.error("redis.get_failed", key=key, error=str(e))
            if await self._ensure_connected():
                try:
                    client = self._require_client()
                    return await client.get(key)
                except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                    logger.error("redis.get_retry_failed", key=key, error=str(retry_error))
            return None

    async def getdel(self, key: str) -> str | None:
        """
        Атомарно вернуть и удалить ключ.

        Если Redis недоступен после retry — поднимает `RedisOperationError`,
        потому что caller (one-shot токен, in-flight handoff) не может
        перепутать "ключа не было" и "не смогли достучаться до Redis".
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"getdel({key}): Redis is unavailable after retry")
        client = self._require_client()
        try:
            return await client.getdel(key)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            logger.error("redis.getdel_failed", key=key, error=str(primary_error))

        lua = "local v = redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]) end; return v"
        if not await self._ensure_connected():
            raise RedisOperationError(f"getdel({key}) lua: Redis is unavailable after retry")
        try:
            client = self._require_client()
            lua_result = await client.eval(lua, 1, key)
        except (RedisError, OSError, asyncio.TimeoutError) as lua_error:
            raise RedisOperationError(f"getdel({key}) lua: {lua_error}") from lua_error
        if lua_result is None or isinstance(lua_result, str):
            return lua_result
        raise RedisOperationError(f"getdel({key}) lua returned non-string: {type(lua_result).__name__}")

    async def set(self, key: str, value: str, *, ttl: int) -> bool:
        """Устанавливает значение по ключу с обязательным TTL (секунды)."""
        if ttl <= 0:
            raise ValueError("ttl must be a positive number of seconds")
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
                logger.error("redis.set_failed", key=key, error=str(e))
                return False
        return False

    async def set_persist(self, key: str, value: str) -> None:
        """SET без expiry. Redis недоступен — RedisOperationError."""
        if not await self._ensure_connected():
            raise RedisOperationError(f"set_persist({key}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            _ = await client.set(key, value)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"set_persist({key}): Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                _ = await client.set(key, value)
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"set_persist({key}): {retry_error}") from retry_error

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        """
        `SET key value NX EX ttl`. True только если ключ раньше отсутствовал.

        Атомарная команда: при Redis-ошибке поднимает `RedisOperationError`.
        Вызывающий код (distributed lock, idempotency guard, dedupe) не может
        интерпретировать "Redis недоступен" как "лок взят/не взят" — это
        прямой путь к double-execution.
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"set_nx({key}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            ok = await client.set(key, value, nx=True, ex=ttl_seconds)
            return bool(ok)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            logger.error("redis.set_nx_failed", key=key, error=str(primary_error))
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"set_nx({key}): Redis is unavailable after retry"
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
            logger.error("redis.setex_failed", key=key, error=str(e))
            return False

    async def sadd(self, key: str, *members: str) -> int:
        """Добавляет members в Redis SET. При недоступности Redis — RedisOperationError."""
        if not members:
            return 0
        if not await self._ensure_connected():
            raise RedisOperationError(f"sadd({key}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            return await client.sadd(key, *members)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"sadd({key}): Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                return await client.sadd(key, *members)
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"sadd({key}): {retry_error}") from retry_error

    async def srem(self, key: str, *members: str) -> int:
        """Удаляет members из Redis SET. При недоступности Redis — RedisOperationError."""
        if not members:
            return 0
        if not await self._ensure_connected():
            raise RedisOperationError(f"srem({key}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            return await client.srem(key, *members)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"srem({key}): Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                return await client.srem(key, *members)
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"srem({key}): {retry_error}") from retry_error

    async def smembers(self, key: str) -> set[str]:
        """Читает members Redis SET. Пустой set только если ключа нет."""
        return await self._read_command(
            f"smembers({key})",
            lambda client: client.smembers(key),
        )

    async def delete(self, *keys: str) -> int:
        """
        Удаляет ключи.

        Атомарная команда: при Redis-ошибке поднимает `RedisOperationError`.
        Тихий `return 0` маскирует "не смогли удалить" под "ключей не было".
        """
        if not await self._ensure_connected():
            raise RedisOperationError(f"delete({keys}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            return await client.delete(*keys)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            raise RedisOperationError(f"delete({keys}): {e}") from e

    async def exists(self, *keys: str) -> int:
        """Проверяет существование ключей (EXISTS)."""
        if not keys:
            return 0
        if not await self._ensure_connected():
            return 0
        try:
            client = self._require_client()
            return await client.exists(*keys)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.error("redis.exists_failed", keys=keys, error=str(e))
            return 0

    async def scan_keys(self, match: str, *, count: int = 500) -> list[str]:
        """SCAN по шаблону; возвращает все совпавшие ключи."""
        return await self._read_command(
            f"scan_keys({match})",
            lambda client: client.scan_keys(match, count=count),
        )

    async def _read_command[T](
        self,
        operation_name: str,
        command: Callable[[_RedisSdkConnection], Awaitable[T]],
    ) -> T:
        if not await self._ensure_connected():
            raise RedisOperationError(f"{operation_name}: Redis is unavailable after retry")
        try:
            client = self._require_client()
            return await command(client)
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    f"{operation_name}: Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                return await command(client)
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"{operation_name}: {retry_error}") from retry_error

    async def scan_all_keys(self, *, count: int = 500) -> list[str]:
        """SCAN всех ключей текущей БД."""
        return await self._read_command(
            "scan_all_keys",
            lambda client: client.scan_all_keys(count=count),
        )

    async def dbsize(self) -> int:
        """Количество ключей в текущей БД (DBSIZE)."""
        return await self._read_command("dbsize", lambda client: client.dbsize())

    async def ttl(self, key: str) -> int:
        """TTL ключа в секундах (-2 отсутствует, -1 без expiry)."""
        return await self._read_command("ttl", lambda client: client.ttl(key))

    async def ttl_batch(self, keys: list[str]) -> list[int]:
        """TTL для списка ключей одним pipeline."""
        if not keys:
            return []
        if not await self._ensure_connected():
            raise RedisOperationError("ttl_batch: Redis is unavailable after retry")
        try:
            client = self._require_client()
            pipeline = client.pipeline()
            for key in keys:
                _ = pipeline.ttl(key)
            ttl_results = await pipeline.execute()
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    "ttl_batch: Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                pipeline = client.pipeline()
                for key in keys:
                    _ = pipeline.ttl(key)
                ttl_results = await pipeline.execute()
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"ttl_batch: {retry_error}") from retry_error
        parsed: list[int] = []
        for ttl_value in ttl_results:
            if not isinstance(ttl_value, int):
                raise RedisOperationError("ttl_batch: non-int ttl in pipeline result")
            parsed.append(ttl_value)
        return parsed

    async def get_batch(self, keys: list[str]) -> list[str | None]:
        """GET для списка ключей одним pipeline. Redis недоступен — RedisOperationError."""
        if not keys:
            return []
        if not await self._ensure_connected():
            raise RedisOperationError("get_batch: Redis is unavailable after retry")
        try:
            client = self._require_client()
            pipeline = client.pipeline()
            for key in keys:
                _ = pipeline.get(key)
            get_results = await pipeline.execute()
        except (RedisError, OSError, asyncio.TimeoutError) as primary_error:
            if not await self._ensure_connected():
                raise RedisOperationError(
                    "get_batch: Redis is unavailable after retry"
                ) from primary_error
            try:
                client = self._require_client()
                pipeline = client.pipeline()
                for key in keys:
                    _ = pipeline.get(key)
                get_results = await pipeline.execute()
            except (RedisError, OSError, asyncio.TimeoutError) as retry_error:
                raise RedisOperationError(f"get_batch: {retry_error}") from retry_error
        parsed: list[str | None] = []
        for value in get_results:
            if value is None:
                parsed.append(None)
                continue
            if not isinstance(value, str):
                raise RedisOperationError(
                    f"get_batch: non-str value in pipeline result: {type(value).__name__}"
                )
            parsed.append(value)
        return parsed

    async def xlen(self, stream: str) -> int:
        """Длина Redis Stream (XLEN)."""
        return await self._read_command("xlen", lambda client: client.xlen(stream))

    async def memory_usage(self, key: str) -> int | None:
        """Память ключа в байтах (MEMORY USAGE); None если ключ отсутствует."""
        return await self._read_command(
            "memory_usage",
            lambda client: client.memory_usage(key),
        )

    async def info_memory(self) -> RedisMemoryInfo:
        """INFO memory: used_memory, used_memory_rss, maxmemory."""
        return await self._read_command(
            "info_memory",
            lambda client: client.info_memory(),
        )

    async def eval(self, script: str, numkeys: int, *keys_and_args: JsonValue) -> JsonValue:
        """Выполняет Lua-скрипт (атомарные read-modify-write на стороне Redis)."""
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected after retries")
        client = self._require_client()
        return require_json_value(await client.eval(script, numkeys, *keys_and_args), "redis.eval")

    async def rpush(self, key: str, *values: str, ttl_seconds: int) -> int:
        """
        Добавляет значения в конец списка (RPUSH) и выставляет TTL на ключ.

        Операция записи поднимает ``RedisOperationError``, чтобы вызывающий код
        не считал, что событие записано, когда Redis недоступен.
        """
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be a positive number of seconds")
        if not values:
            raise ValueError("rpush requires at least one value")
        if not await self._ensure_connected():
            raise RedisOperationError(f"rpush({key}): Redis is unavailable after retry")
        try:
            client = self._require_client()
            pushed = await client.rpush(key, *values)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            raise RedisOperationError(f"rpush({key}): {e}") from e
        expire_script = (
            "if redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1])) == 0 then "
            "return redis.error_reply('EXPIRE failed') end return 1"
        )
        try:
            client = self._require_client()
            expire_ok = await client.eval(expire_script, 1, key, ttl_seconds)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            raise RedisOperationError(f"rpush_expire({key}): {e}") from e
        if expire_ok != 1:
            raise RedisOperationError(f"rpush_expire({key}): unexpected eval result")
        return pushed

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка (LRANGE), включая обе границы."""
        if not await self._ensure_connected():
            return []
        try:
            client = self._require_client()
            return await client.lrange(key, start, end)
        except (RedisError, OSError, asyncio.TimeoutError) as e:
            logger.error("redis.lrange_failed", key=key, error=str(e))
            return []

    async def ping(self) -> bool:
        """Проверяет соединение с Redis."""
        self._rebind_if_event_loop_changed()
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
        """Публикует сообщение в канал Pub/Sub с auto-reconnect и повтором"""
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected after retries")

        # Одна повторная попытка публикации
        for attempt in range(2):
            try:
                client = self._require_client()
                return await client.publish(channel, message)
            except Exception as e:
                if attempt == 0:
                    logger.warning("redis.publish_retry", error=str(e))
                    if await self._ensure_connected():
                        continue
                logger.error("redis.publish_failed", error=str(e))
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
        Подписывается на канал и отдаёт сообщения через yield с auto-reconnect.

        Idle-timeout: сбрасывается при каждом полученном сообщении.
        Max-timeout: абсолютный предел жизни подписки (защита от утечек).

        Аргументы:
            channel: Имя канала
            timeout: Idle-таймаут в секундах (сбрасывается при каждом сообщении)
            max_timeout: Абсолютный потолок жизни подписки
            ready_event: Event для сигнализации о готовности подписки

        Генерирует:
            Сообщения из канала
        """
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected")

        client = self._require_client()
        pubsub = client.pubsub()

        try:
            await pubsub.subscribe(channel)
            logger.debug("redis.subscribed", channel=channel)

            if ready_event:
                ready_event.set()

            start_time = time.monotonic()
            last_activity = start_time

            while True:
                now = time.monotonic()
                if now - start_time >= max_timeout:
                    logger.warning("clients.subscription.max.timeout.s", channel=channel, now=now - start_time)
                    break
                if now - last_activity >= timeout:
                    logger.warning("clients.subscription.idle.timeout.s.idle", channel=channel, now=now - last_activity)
                    break

                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message["type"] == "message":
                        last_activity = time.monotonic()
                        yield message["data"]
                except (RedisError, OSError, asyncio.TimeoutError) as e:
                    logger.error("redis.receive_failed", channel=channel, error=str(e))
                    if await self._ensure_connected():
                        try:
                            await pubsub.unsubscribe(channel)
                            await pubsub.aclose()
                            client = self._require_client()
                            pubsub = client.pubsub()
                            await pubsub.subscribe(channel)
                            logger.info("redis.resubscribed", channel=channel)
                        except (RedisError, OSError, asyncio.TimeoutError) as resub_error:
                            logger.error("redis.resubscribe_failed", channel=channel, error=str(resub_error))
                            break
                    else:
                        break
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except (RedisError, OSError, asyncio.TimeoutError):
                pass
