"""
Настройка подключения к базе данных.
"""

import asyncio
import logging
from typing import AsyncGenerator, Dict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker

from app.core.config import settings
from app.db.models import Base

logger = logging.getLogger(__name__)

# Словари для хранения engine и session factory для каждого event loop
_engines: Dict[int, AsyncEngine] = {}
_session_factories: Dict[int, async_sessionmaker] = {}


async def get_engine() -> AsyncEngine:
    """Лениво создает engine для текущего event loop"""

    current = asyncio.get_running_loop()
    loop_id = id(current)

    # Если engine для этого loop'а уже есть, возвращаем его
    if loop_id in _engines:
        return _engines[loop_id]

    # Создаем новый engine для этого event loop
    logger.debug(f"🔧 Создаем новый engine для event loop {loop_id}")
    engine = create_async_engine(
        settings.database.url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=3600,
        pool_size=5,
        max_overflow=10,
    )
    _engines[loop_id] = engine

    return engine


async def get_session_factory() -> async_sessionmaker:
    """Лениво создает session factory для текущего event loop"""

    current = asyncio.get_running_loop()
    loop_id = id(current)

    # Если session factory для этого loop'а уже есть, возвращаем его
    if loop_id in _session_factories:
        return _session_factories[loop_id]

    # Создаем новый session factory для этого event loop
    engine = await get_engine()
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    _session_factories[loop_id] = session_factory

    return session_factory


class AsyncSessionLocalProxy:
    """Proxy для ленивой инициализации session factory"""

    def __call__(self):
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop_id = id(loop)

            if loop_id not in _session_factories:
                raise RuntimeError(
                    "Session factory не инициализирован. "
                    "Используйте await get_session_factory() или get_container().session_factory"
                )
            return _session_factories[loop_id]()
        except RuntimeError as e:
            if "no running event loop" in str(e) or "no current event loop" in str(e):
                raise RuntimeError(
                    "AsyncSessionLocal требует event loop. "
                    "Используйте get_container().session_factory в async контексте"
                )
            raise


AsyncSessionLocal = AsyncSessionLocalProxy()


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
    """Закрывает соединения с БД для всех event loop'ов"""
    global _engines, _session_factories

    if _engines:
        logger.info(f"Закрываем {len(_engines)} engine(s)")
        for loop_id, engine in _engines.items():
            try:
                await engine.dispose()
                logger.debug(f"✅ Engine для loop {loop_id} закрыт")
            except Exception as e:
                logger.error(f"❌ Ошибка при закрытии engine для loop {loop_id}: {e}")

        _engines.clear()
        _session_factories.clear()
        logger.info("Все соединения с БД закрыты")


