"""
Настройка подключения к базе данных.
"""
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger(__name__)

# Создаем асинхронный движок
engine = create_async_engine(
    settings.database.url,
    echo=False,  # Отключаем логирование SQL запросов
    pool_pre_ping=True,   # Проверка соединений перед использованием
    pool_recycle=3600,    # Пересоздание соединений каждый час
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии БД в FastAPI.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка в сессии БД: {e}")
            raise
        finally:
            await session.close()


async def create_tables():
    """Создает таблицы в БД"""
    from app.db.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    logger.info("Таблицы созданы")


async def drop_tables():
    """Удаляет все таблицы"""
    from app.db.models import Base
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    logger.info("Таблицы удалены")


async def close_db():
    """Закрывает соединения с БД"""
    await engine.dispose()
    logger.info("Соединения с БД закрыты")
