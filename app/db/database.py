"""
Настройка подключения к базе данных.
"""

import asyncio
import logging
import weakref
from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Кэш engine и session factory по event loop
_engines: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_session_factories: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _get_loop_id() -> int:
    """Получает ID текущего event loop для кэширования"""
    try:
        loop = asyncio.get_running_loop()
        return id(loop)
    except RuntimeError:
        # Если нет запущенного loop, используем id текущего потока
        import threading
        return id(threading.current_thread())


async def get_engine() -> AsyncEngine:
    """Лениво создает engine для текущего event loop"""
    loop_id = _get_loop_id()

    if loop_id in _engines:
        return _engines[loop_id]

    import os
    logger.debug(f"🔧 Создаем engine для event loop {loop_id}")

    # В тестах используем NullPool чтобы избежать проблем с event loop
    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None

    if is_testing:
        engine = create_async_engine(
            settings.database.url,
            echo=False,
            poolclass=NullPool,
        )
        logger.debug(f"🔧 Engine создан с NullPool для тестов (loop {loop_id})")
    else:
        engine = create_async_engine(
            settings.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
        )
        logger.debug(f"🔧 Engine создан (loop {loop_id})")

    _engines[loop_id] = engine
    return engine


async def get_session_factory() -> async_sessionmaker:
    """Лениво создает session factory для текущего event loop"""
    loop_id = _get_loop_id()

    if loop_id in _session_factories:
        return _session_factories[loop_id]

    engine = await get_engine()
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    _session_factories[loop_id] = session_factory
    logger.debug(f"✅ Session factory создана (loop {loop_id})")
    return session_factory


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
    """Закрывает соединения с БД для текущего event loop"""
    loop_id = _get_loop_id()

    engine = _engines.get(loop_id)
    if engine is not None:
        logger.info(f"Закрываем engine для event loop {loop_id}")
        try:
            await engine.dispose()
            logger.debug(f"✅ Engine закрыт (loop {loop_id})")
        except Exception as e:
            logger.error(f"❌ Ошибка при закрытии engine: {e}")

        # Удаляем из кэша
        _engines.pop(loop_id, None)
        _session_factories.pop(loop_id, None)
        logger.info(f"Соединения с БД закрыты (loop {loop_id})")


