"""
База для Sync репозиториев - работа с SQLAlchemy напрямую.

Паттерн CRM: SyncDatabase (engine + session_factory) + BaseSyncRepository
с автоматической изоляцией по company_id из контекста.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Generic, TypeVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm.attributes import InstrumentedAttribute

from core.config import get_settings
from core.context import require_active_company
from core.db.utils import get_rowcount
from core.logging import get_logger

logger = get_logger(__name__)
T = TypeVar("T", bound=DeclarativeBase)


class SyncDatabase:
    """
    Менеджер подключения к Sync БД.

    Создает engine и session factory для работы с PostgreSQL.
    """

    _instance: ClassVar[SyncDatabase | None] = None

    def __init__(self, db_url: str) -> None:
        self._engine: AsyncEngine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def get_instance(cls, db_url: str | None = None) -> "SyncDatabase":
        """Singleton для Sync database"""
        if cls._instance is None:
            if db_url is None:
                settings = get_settings()
                db_url = settings.database.sync_url
                if not db_url:
                    raise ValueError("database.sync_url не задан")
            cls._instance = cls(db_url)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Сброс singleton (для тестов)"""
        cls._instance = None

    def session(self) -> AsyncSession:
        """Создает новую сессию"""
        return self._session_factory()


class BaseSyncRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для Sync с реляционной БД.

    Обеспечивает CRUD, пагинацию и автоматическую изоляцию по company_id.
    """

    def __init__(self, db: SyncDatabase) -> None:
        self._db: SyncDatabase = db

    def _get_company_id(self) -> str:
        """Получает company_id из контекста. Middleware гарантирует наличие."""
        return require_active_company().company_id

    @property
    @abstractmethod
    def model_class(self) -> type[T]:
        """Класс SQLAlchemy модели"""
        pass

    @property
    @abstractmethod
    def id_column(self) -> InstrumentedAttribute[str]:
        """Типизированная SQLAlchemy-колонка первичного идентификатора."""
        pass

    @property
    def company_id_column(self) -> InstrumentedAttribute[str] | None:
        """Типизированная SQLAlchemy-колонка company_id, если таблица tenant-scoped."""
        return None

    async def get(self, entity_id: str) -> T | None:
        """Получает запись по ID"""
        async with self._db.session() as session:
            stmt = select(self.model_class).where(self.id_column == entity_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_many(self, entity_ids: list[str]) -> list[T]:
        """Получает несколько записей по списку ID"""
        if not entity_ids:
            return []

        async with self._db.session() as session:
            stmt = select(self.model_class).where(self.id_column.in_(entity_ids))
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def create(self, entity: T) -> T:
        """Создает новую запись"""
        async with self._db.session() as session:
            session.add(entity)
            await session.commit()
            await session.refresh(entity)
            return entity

    async def update(self, entity: T) -> T:
        """Обновляет запись"""
        async with self._db.session() as session:
            merged = await session.merge(entity)
            await session.commit()
            await session.refresh(merged)
            return merged

    async def delete(self, entity_id: str) -> bool:
        """Удаляет запись по ID"""
        async with self._db.session() as session:
            stmt = delete(self.model_class).where(self.id_column == entity_id)
            result = await session.execute(stmt)
            await session.commit()
            return get_rowcount(result) > 0

    async def list(
        self,
        *,
        limit: int,
        offset: int = 0,
        company_id: str | None = None,
    ) -> list[T]:
        """Возвращает страницу записей, фильтруя по company_id."""
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(self.model_class)
            company_col = self.company_id_column
            if company_col is not None:
                stmt = stmt.where(company_col == cid)
            stmt = stmt.limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count(self, company_id: str | None = None) -> int:
        """Считает количество записей для компании."""
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(func.count()).select_from(self.model_class)
            company_col = self.company_id_column
            if company_col is not None:
                stmt = stmt.where(company_col == cid)
            result = await session.execute(stmt)
            return result.scalar_one()


def get_sync_db() -> SyncDatabase:
    """Получает singleton Sync database"""
    return SyncDatabase.get_instance()
