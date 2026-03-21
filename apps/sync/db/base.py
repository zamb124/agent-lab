"""
База для Sync репозиториев - работа с SQLAlchemy напрямую.

Паттерн CRM: SyncDatabase (engine + session_factory) + BaseSyncRepository
с автоматической изоляцией по company_id из контекста.
"""

import logging
from typing import Generic, TypeVar, Optional, List, Type
from abc import ABC, abstractmethod

from sqlalchemy import select, delete, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from apps.sync.db.models import Base
from core.context import get_context

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=DeclarativeBase)


class SyncDatabase:
    """
    Менеджер подключения к Sync БД.

    Создает engine и session factory для работы с PostgreSQL.
    """

    _instance: Optional["SyncDatabase"] = None

    def __init__(self, db_url: str):
        self._engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=5,
            max_overflow=10,
        )
        self._session_factory = async_sessionmaker(
            bind=self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @classmethod
    def get_instance(cls, db_url: Optional[str] = None) -> "SyncDatabase":
        """Singleton для Sync database"""
        if cls._instance is None:
            if db_url is None:
                from core.config import get_settings
                settings = get_settings()
                db_url = settings.database.sync_url or settings.database.url
            cls._instance = cls(db_url)
        return cls._instance

    @classmethod
    def reset(cls):
        """Сброс singleton (для тестов)"""
        cls._instance = None

    def session(self) -> AsyncSession:
        """Создает новую сессию"""
        return self._session_factory()

    def _sync_tables(self):
        """Возвращает только таблицы sync (с префиксом sync_)."""
        return [
            t for t in Base.metadata.sorted_tables
            if t.name.startswith("sync_")
        ]

    async def create_tables(self, drop_existing: bool = False):
        """
        Создает таблицы Sync (только с префиксом sync_).

        Args:
            drop_existing: Если True - сначала удаляет существующие таблицы (для тестов).
        """
        tables = self._sync_tables()
        async with self._engine.begin() as conn:
            if drop_existing:
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables)
                )
            await conn.run_sync(
                lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables, checkfirst=True)
            )
            await self._ensure_schema_columns(conn)
        logger.info(f"Sync таблицы созданы: {[t.name for t in tables]}")

    async def _ensure_schema_columns(self, conn) -> None:
        """
        Добавляет колонки, появившиеся в моделях после создания таблиц.

        create_all() не изменяет уже существующие таблицы — без этого запросы ORM
        падают с UndefinedColumnError на старых инсталляциях.
        """
        statements = [
            (
                "sync_channels.pinned_message_ids",
                "ALTER TABLE sync_channels ADD COLUMN IF NOT EXISTS "
                "pinned_message_ids JSONB NOT NULL DEFAULT '[]'::jsonb",
            ),
            (
                "sync_messages.reactions",
                "ALTER TABLE sync_messages ADD COLUMN IF NOT EXISTS "
                "reactions JSONB NOT NULL DEFAULT '[]'::jsonb",
            ),
            (
                "sync_messages.deleted_at",
                "ALTER TABLE sync_messages ADD COLUMN IF NOT EXISTS "
                "deleted_at TIMESTAMP WITH TIME ZONE NULL",
            ),
            (
                "sync_messages.forwarded_from_channel_id",
                "ALTER TABLE sync_messages ADD COLUMN IF NOT EXISTS "
                "forwarded_from_channel_id VARCHAR(64) NULL",
            ),
            (
                "sync_messages.forwarded_from_channel_name",
                "ALTER TABLE sync_messages ADD COLUMN IF NOT EXISTS "
                "forwarded_from_channel_name VARCHAR(255) NULL",
            ),
        ]
        for _label, sql in statements:
            await conn.execute(text(sql))

    async def drop_tables(self):
        """Удаляет таблицы Sync (для тестов)"""
        tables = self._sync_tables()
        async with self._engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: Base.metadata.drop_all(sync_conn, tables=tables)
            )


class BaseSyncRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для Sync с реляционной БД.

    Обеспечивает CRUD, пагинацию и автоматическую изоляцию по company_id.
    """

    def __init__(self, db: SyncDatabase):
        self._db = db

    def _get_company_id(self) -> str:
        """Получает company_id из контекста. Middleware гарантирует наличие."""
        context = get_context()
        return context.active_company.company_id

    @property
    @abstractmethod
    def model_class(self) -> Type[T]:
        """Класс SQLAlchemy модели"""
        pass

    @property
    @abstractmethod
    def id_field(self) -> str:
        """Имя поля с ID"""
        pass

    @property
    def company_id_field(self) -> Optional[str]:
        """Имя поля company_id (None если таблица без изоляции)"""
        return "company_id"

    def _get_id_column(self):
        return getattr(self.model_class, self.id_field)

    def _get_company_column(self):
        if self.company_id_field is None:
            return None
        return getattr(self.model_class, self.company_id_field, None)

    async def get(self, entity_id: str) -> Optional[T]:
        """Получает запись по ID"""
        async with self._db.session() as session:
            stmt = select(self.model_class).where(
                self._get_id_column() == entity_id
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()

    async def get_many(self, entity_ids: List[str]) -> List[T]:
        """Получает несколько записей по списку ID"""
        if not entity_ids:
            return []

        async with self._db.session() as session:
            stmt = select(self.model_class).where(
                self._get_id_column().in_(entity_ids)
            )
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
            stmt = delete(self.model_class).where(
                self._get_id_column() == entity_id
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount > 0

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        company_id: Optional[str] = None,
    ) -> List[T]:
        """Получает список записей с пагинацией, фильтруя по company_id."""
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(self.model_class)
            company_col = self._get_company_column()
            if company_col is not None:
                stmt = stmt.where(company_col == cid)
            stmt = stmt.limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def count(self, company_id: Optional[str] = None) -> int:
        """Считает количество записей для компании."""
        cid = company_id or self._get_company_id()

        async with self._db.session() as session:
            stmt = select(func.count()).select_from(self.model_class)
            company_col = self._get_company_column()
            if company_col is not None:
                stmt = stmt.where(company_col == cid)
            result = await session.execute(stmt)
            return result.scalar() or 0


def get_sync_db() -> SyncDatabase:
    """Получает singleton Sync database"""
    return SyncDatabase.get_instance()
