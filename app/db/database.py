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

# Глобальные переменные для ленивой инициализации
_engine = None
_AsyncSessionLocal = None
_current_loop = None


async def get_engine():
    """Лениво создает engine в текущем event loop"""
    global _engine, _current_loop
    import asyncio
    
    current = asyncio.get_event_loop()
    
    # Если engine создан в другом event loop, пересоздаем
    if _engine is not None and _current_loop is not None and _current_loop != current:
        await _engine.dispose()
        _engine = None
    
    if _engine is None:
        _engine = create_async_engine(
            settings.database.url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
        )
        _current_loop = current
        
    return _engine


async def get_session_factory():
    """Лениво создает session factory в текущем event loop"""
    global _AsyncSessionLocal
    
    engine = await get_engine()
    
    # Всегда пересоздаем session_factory для текущего engine
    _AsyncSessionLocal = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    
    return _AsyncSessionLocal


class AsyncSessionLocalProxy:
    """Proxy для ленивой инициализации session factory"""
    
    def __call__(self):
        import asyncio
        try:
            loop = asyncio.get_event_loop()
            if _AsyncSessionLocal is None:
                raise RuntimeError(
                    "Session factory не инициализирован. "
                    "Используйте await get_session_factory() или get_container().session_factory"
                )
            return _AsyncSessionLocal()
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
    """Закрывает соединения с БД"""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    logger.info("Соединения с БД закрыты")


