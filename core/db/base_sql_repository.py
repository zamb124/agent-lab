"""
Базовый репозиторий для работы с SQL таблицами через asyncpg.
"""

from abc import ABC
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg
else:
    try:
        import asyncpg
    except ImportError:
        asyncpg = None

from core.logging import get_logger

logger = get_logger(__name__)


class BaseSQLRepository(ABC):
    """
    Базовый репозиторий для работы с SQL таблицами через asyncpg.
    
    В отличие от BaseRepository (Key-Value JSONB), этот класс
    предназначен для работы с реляционными таблицами напрямую.
    """

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: Optional["asyncpg.Pool"] = None

    async def connect(self) -> None:
        """Создать connection pool"""
        if asyncpg is None:
            raise RuntimeError("asyncpg не установлен")
        if not self._pool:
            self._pool = await asyncpg.create_pool(
                self.database_url,
                min_size=2,
                max_size=10,
            )
            logger.info(f"{self.__class__.__name__}: подключение к PostgreSQL установлено")

    async def close(self) -> None:
        """Закрыть connection pool"""
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info(f"{self.__class__.__name__}: соединение закрыто")

    def _ensure_connected(self) -> None:
        """Проверяет что pool инициализирован"""
        if not self._pool:
            raise RuntimeError(
                f"{self.__class__.__name__} не подключен к БД. "
                f"Вызовите connect() перед использованием."
            )

    async def execute(self, query: str, *args: Any) -> str:
        """Выполняет SQL запрос"""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list:
        """Выполняет SELECT и возвращает все строки"""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> Optional[Any]:
        """Выполняет SELECT и возвращает одну строку"""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Optional[Any]:
        """Выполняет SELECT и возвращает одно значение"""
        self._ensure_connected()
        async with self._pool.acquire() as conn:
            return await conn.fetchval(query, *args)

