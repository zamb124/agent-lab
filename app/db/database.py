"""
Настройка подключения к базе данных.
"""

import asyncio
import logging
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Глобальный engine и session factory
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


async def get_engine() -> AsyncEngine:
    """Лениво создает глобальный engine"""
    global _engine

    if _engine is not None:
        return _engine

    import os
    logger.debug("🔧 Создаем глобальный engine")

    # В тестах используем NullPool чтобы избежать проблем с event loop
    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None

    if is_testing:
        _engine = create_async_engine(
            settings.database.url,
            echo=False,
            poolclass=NullPool,
        )
        logger.debug("🔧 Engine создан с NullPool для тестов")
    else:
        _engine = create_async_engine(
            settings.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
        )

    return _engine


async def get_session_factory() -> async_sessionmaker:
    """Лениво создает глобальную session factory"""
    global _session_factory

    if _session_factory is not None:
        return _session_factory

    engine = await get_engine()
    _session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    logger.debug("✅ Session factory создана")
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии БД в FastAPI.
    """
    session_factory = await get_session_factory()
    async with session_factory() as session:
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
            engine = await get_engine()
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
    """Создает таблицы в БД если их нет"""
    await wait_for_db()

    try:
        engine = await get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all, checkfirst=True)
        logger.info("✅ Таблицы проверены/созданы")
    except Exception as e:
        error_msg = str(e)
        if "already exists" in error_msg or "duplicate key" in error_msg:
            logger.info("ℹ️ Таблицы уже существуют, пропускаем создание")
        else:
            logger.error(f"❌ Ошибка при создании таблиц: {e}")
            raise


async def drop_tables():
    """Удаляет все таблицы"""
    engine = await get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    logger.info("Таблицы удалены")


async def close_db():
    """Закрывает соединения с БД"""
    global _engine, _session_factory

    if _engine is not None:
        logger.info("Закрываем engine")
        try:
            await _engine.dispose()
            logger.debug("✅ Engine закрыт")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии engine: {e}")

        _engine = None
        _session_factory = None
        logger.info("Соединения с БД закрыты")


