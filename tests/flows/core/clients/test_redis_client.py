"""
Тесты RedisClient.

Используют реальный Redis без моков.
Проверяют все методы клиента.
"""

import pytest

from apps.flows.config import get_settings
from core.clients.redis_client import RedisClient


class TestRedisClient:
    """Тесты RedisClient."""

    @pytest.fixture
    def redis_client(self):
        """Создает Redis клиент."""
        settings = get_settings()
        client = RedisClient(settings.database.redis_url)
        return client

    @pytest.mark.asyncio
    async def test_connect(self, redis_client):
        """Подключение к Redis."""
        await redis_client.connect()

        ping_result = await redis_client.ping()
        assert ping_result is True

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_set_and_get(self, redis_client):
        """Установка и получение значения."""
        await redis_client.connect()

        key = "test_key_123"
        value = "test_value"

        success = await redis_client.set(key, value)
        assert success is True

        result = await redis_client.get(key)
        assert result == value

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_setex(self, redis_client):
        """Установка значения с TTL."""
        await redis_client.connect()

        key = "test_key_ttl"
        value = "test_value_ttl"
        seconds = 10

        success = await redis_client.setex(key, seconds, value)
        assert success is True

        result = await redis_client.get(key)
        assert result == value

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_delete(self, redis_client):
        """Удаление ключа."""
        await redis_client.connect()

        key = "test_key_delete"
        value = "test_value"

        await redis_client.set(key, value)
        result = await redis_client.get(key)
        assert result == value

        deleted = await redis_client.delete(key)
        assert deleted == 1

        result_after = await redis_client.get(key)
        assert result_after is None

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_delete_multiple(self, redis_client):
        """Удаление нескольких ключей."""
        await redis_client.connect()

        key1 = "test_key_delete_1"
        key2 = "test_key_delete_2"
        key3 = "test_key_delete_3"

        await redis_client.set(key1, "value1")
        await redis_client.set(key2, "value2")
        await redis_client.set(key3, "value3")

        deleted = await redis_client.delete(key1, key2, key3)
        assert deleted == 3

        assert await redis_client.get(key1) is None
        assert await redis_client.get(key2) is None
        assert await redis_client.get(key3) is None

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, redis_client):
        """Получение несуществующего ключа возвращает None."""
        await redis_client.connect()

        result = await redis_client.get("nonexistent_key_xyz")

        assert result is None

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_ping(self, redis_client):
        """Проверка соединения через ping."""
        await redis_client.connect()

        ping_result = await redis_client.ping()
        assert ping_result is True

        await redis_client.close()

    @pytest.mark.asyncio
    async def test_close(self, redis_client):
        """Закрытие соединения."""
        await redis_client.connect()

        ping_before = await redis_client.ping()
        assert ping_before is True

        await redis_client.close()

        ping_after = await redis_client.ping()
        assert ping_after is False

