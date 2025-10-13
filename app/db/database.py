"""
Настройка подключения к базе данных.
"""

import asyncio
import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Создаем асинхронный движок
engine = create_async_engine(
    settings.database.url,
    echo=False,
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,
    max_overflow=10,
)

# Создаем фабрику сессий
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
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


async def wait_for_db(max_retries: int = 30, retry_interval: int = 2):
    """Ожидает готовности БД с повторными попытками"""
    for attempt in range(1, max_retries + 1):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            logger.info(f"✅ БД готова к работе (попытка {attempt}/{max_retries})")
            return
        except Exception as e:
            if attempt < max_retries:
                logger.warning(
                    f"⏳ БД не готова (попытка {attempt}/{max_retries}), "
                    f"повтор через {retry_interval}с: {str(e)[:100]}"
                )
                await asyncio.sleep(retry_interval)
            else:
                logger.error(f"❌ БД недоступна после {max_retries} попыток")
                raise


async def create_tables():
    """Создает таблицы в БД"""
    await wait_for_db()
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("Таблицы созданы")


async def drop_tables():
    """Удаляет все таблицы"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    logger.info("Таблицы удалены")


async def close_db():
    """Закрывает соединения с БД"""
    await engine.dispose()
    logger.info("Соединения с БД закрыты")
