"""
Redis клиент для кэширования, сессий и Pub/Sub streaming.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

try:
    import redis.asyncio as redis
except ImportError:
    redis = None

from core.logging import get_logger
from core.types import JsonValue, require_json_value

logger = get_logger(__name__)


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
        self.redis_url = redis_url
        self._client: Any | None = None
        self._max_retries = max_retries
        self._connection_lock = asyncio.Lock()

    async def connect(self) -> None:
        """Подключается к Redis"""
        if redis is None:
            logger.warning("Redis не установлен, RedisClient будет работать в режиме без подключения")
            return
        try:
            parsed = urlparse(self.redis_url)
            db = int(parsed.path.lstrip("/")) if parsed.path else 0

            self._client = redis.Redis(
                host=parsed.hostname or "localhost",
                port=parsed.port or 6379,
                db=db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                health_check_interval=30,
            )
            await self._client.ping()
            logger.info("RedisClient: подключение к Redis установлено")
        except Exception as e:
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
            # Проверяем текущее соединение
            if self._client:
                try:
                    await self._client.ping()
                    return True
                except Exception:
                    logger.warning("Redis connection lost, reconnecting...")
                    self._client = None

            # Переподключаемся с exponential backoff
            for attempt in range(self._max_retries):
                try:
                    await self.connect()
                    if self._client:
                        logger.info("Redis reconnected successfully")
                        return True
                except Exception as e:
                    if attempt < self._max_retries - 1:
                        wait_time = 2 ** attempt
                        logger.warning(f"Reconnect attempt {attempt+1} failed: {e}, retry in {wait_time}s")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Failed to reconnect to Redis after {self._max_retries} attempts")

            return False

    def _require_client(self) -> Any:
        if self._client is None:
            raise RuntimeError("Redis client not connected after retries")
        return self._client

    async def get(self, key: str) -> str | None:
        """Получает значение по ключу с auto-reconnect"""
        if not await self._ensure_connected():
            return None
        client = self._require_client()

        try:
            return await client.get(key)
        except Exception as e:
            logger.warning(f"Get failed for key {key}: {e}")
            # Одна попытка после переподключения
            if await self._ensure_connected():
                try:
                    client = self._require_client()
                    return await client.get(key)
                except Exception:
                    pass
            return None

    async def getdel(self, key: str) -> str | None:
        """Атомарно возвращает значение и удаляет ключ (Redis GETDEL / fallback Lua)."""
        if not await self._ensure_connected():
            return None
        client = self._require_client()
        try:
            getter = getattr(client, "getdel", None)
            if callable(getter):
                return await client.getdel(key)
        except Exception as e:
            logger.warning(f"getdel failed for key {key}: {e}")

        lua = "local v = redis.call('GET', KEYS[1]); if v then redis.call('DEL', KEYS[1]) end; return v"
        try:
            if await self._ensure_connected():
                client = self._require_client()
                return await client.eval(lua, 1, key)
        except Exception as e:
            logger.warning(f"getdel lua failed for key {key}: {e}")
        return None

    async def set(self, key: str, value: str, ttl: int | None = None) -> bool:
        """Устанавливает значение по ключу с auto-reconnect"""
        if not await self._ensure_connected():
            return False

        for attempt in range(2):
            try:
                client = self._require_client()
                await client.set(key, value, ex=ttl)
                return True
            except Exception as e:
                if attempt == 0 and await self._ensure_connected():
                    continue
                logger.warning(f"Set failed for key {key}: {e}")
                return False
        return False

    async def set_nx(self, key: str, value: str, ttl_seconds: int) -> bool:
        """SET key value NX EX ttl — True только если ключ раньше отсутствовал."""
        if not await self._ensure_connected():
            return False
        try:
            client = self._require_client()
            ok = await client.set(key, value, nx=True, ex=ttl_seconds)
            return bool(ok)
        except Exception as e:
            logger.warning(f"set_nx failed for key {key}: {e}")
            if await self._ensure_connected():
                try:
                    client = self._require_client()
                    ok = await client.set(key, value, nx=True, ex=ttl_seconds)
                    return bool(ok)
                except Exception as e2:
                    logger.warning(f"set_nx retry failed for key {key}: {e2}")
            return False

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        """Устанавливает значение с TTL"""
        if not await self._ensure_connected():
            return False
        try:
            client = self._require_client()
            await client.setex(key, seconds, value)
            return True
        except Exception as e:
            logger.warning(f"RedisClient: ошибка установки ключа {key} с TTL: {e}")
            return False

    async def delete(self, *keys: str) -> int:
        """Удаляет ключи"""
        if not await self._ensure_connected():
            return 0
        try:
            client = self._require_client()
            return await client.delete(*keys)
        except Exception as e:
            logger.warning(f"RedisClient: ошибка удаления ключей: {e}")
            return 0

    async def eval(self, script: str, numkeys: int, *keys_and_args: JsonValue) -> JsonValue:
        """Выполняет Lua-скрипт (атомарные read-modify-write на стороне Redis)."""
        if not await self._ensure_connected():
            raise RuntimeError("Redis client not connected after retries")
        client = self._require_client()
        return require_json_value(await client.eval(script, numkeys, *keys_and_args), "redis.eval")

    async def rpush(self, key: str, *values: str) -> int:
        """Добавляет значения в конец списка (RPUSH)."""
        if not await self._ensure_connected():
            return 0
        try:
            client = self._require_client()
            return await client.rpush(key, *values)
        except Exception as e:
            logger.warning(f"RedisClient: ошибка RPUSH в {key}: {e}")
            return 0

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        """Возвращает срез списка (LRANGE), включая обе границы."""
        if not await self._ensure_connected():
            return []
        try:
            client = self._require_client()
            return await client.lrange(key, start, end)
        except Exception as e:
            logger.warning(f"RedisClient: ошибка LRANGE из {key}: {e}")
            return []

    async def ping(self) -> bool:
        """Проверяет соединение с Redis"""
        if not self._client:
            return False
        try:
            await self._client.ping()
            return True
        except Exception:
            return False

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
                        "Subscription idle-timeout on %s after %.1fs idle", channel, now - last_activity
                    )
                    break

                try:
                    message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                    if message and message["type"] == "message":
                        last_activity = time.monotonic()
                        yield message["data"]
                except Exception as e:
                    logger.warning(f"Error receiving message from {channel}: {e}")
                    if await self._ensure_connected():
                        try:
                            await pubsub.unsubscribe(channel)
                            await pubsub.aclose()
                            client = self._require_client()
                            pubsub = client.pubsub()
                            await pubsub.subscribe(channel)
                            logger.info(f"Resubscribed to {channel}")
                        except Exception as resub_error:
                            logger.error(f"Failed to resubscribe to {channel}: {resub_error}")
                            break
                    else:
                        break
        finally:
            try:
                await pubsub.unsubscribe(channel)
                await pubsub.aclose()
            except Exception:
                pass
