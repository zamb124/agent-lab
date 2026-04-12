"""
База для CRM репозиториев - работа с SQLAlchemy напрямую.

В отличие от agents, где используется key-value storage,
CRM использует реляционную БД для:
- Эффективной фильтрации по индексам
- JOIN'ов между таблицами
- Агрегаций и сортировки
"""

import logging
from typing import Generic, TypeVar, Optional, List, Type
from abc import ABC, abstractmethod

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from core.context import get_context

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=DeclarativeBase)


class CRMDatabase:
    """
    Менеджер подключения к CRM БД.
    
    Создает engine и session factory для работы с PostgreSQL.
    """
    
    _instance: Optional["CRMDatabase"] = None
    
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
            expire_on_commit=False
        )
    
    @classmethod
    def get_instance(cls, db_url: Optional[str] = None) -> "CRMDatabase":
        """Singleton для CRM database"""
        if cls._instance is None:
            if db_url is None:
                from core.config import get_settings
                db_url = get_settings().database.crm_url
                if not db_url:
                    raise ValueError("database.crm_url не задан")
            cls._instance = cls(db_url)
        return cls._instance
    
    @classmethod
    def reset(cls):
        """Сброс singleton (для тестов)"""
        cls._instance = None
    
    def session(self) -> AsyncSession:
        """Создает новую сессию"""
        return self._session_factory()


class BaseCRMRepository(ABC, Generic[T]):
    """
    Базовый репозиторий для CRM с реляционной БД.
    
    Работает напрямую с SQLAlchemy моделями, обеспечивая:
    - Индексированные запросы
    - Пагинацию на уровне БД
    - Эффективную фильтрацию
    - Автоматическую изоляцию по company_id из контекста
    """
    
    def __init__(self, db: CRMDatabase):
        self._db = db
    
    def _get_company_id(self) -> str:
        """
        Получает company_id из контекста.
        Middleware гарантирует наличие контекста.
        """
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
    
    def _get_id_column(self):
        """Получает колонку ID"""
        return getattr(self.model_class, self.id_field)
    
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
    
    async def list(
        self,
        *,
        limit: int,
        offset: int = 0,
    ) -> list[T]:
        """Возвращает страницу записей."""
        async with self._db.session() as session:
            stmt = select(self.model_class).limit(limit).offset(offset)
            result = await session.execute(stmt)
            return list(result.scalars().all())
    
    async def count(self) -> int:
        """Считает общее количество записей"""
        async with self._db.session() as session:
            stmt = select(func.count()).select_from(self.model_class)
            result = await session.execute(stmt)
            return result.scalar() or 0


def get_crm_db() -> CRMDatabase:
    """Получает singleton CRM database"""
    return CRMDatabase.get_instance()

