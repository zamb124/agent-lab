"""
Настройка подключения к базе данных.

ВАЖНО: НЕ ИСПОЛЬЗУЕТ try-except для фолбэков.
Если БД недоступна - приложение падает (fail-fast).
"""

import asyncio
import logging
import os
import weakref
from typing import AsyncGenerator, Optional, List
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, AsyncEngine, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from core.config import get_settings
from core.db.models import (
    Base,
)

logger = logging.getLogger(__name__)

_engines: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
_session_factories: weakref.WeakValueDictionary = weakref.WeakValueDictionary()


def _get_loop_id() -> int:
    """Получает ID текущего event loop для кэширования"""
    loop = asyncio.get_running_loop()
    return id(loop)


async def get_engine(db_url: Optional[str] = None) -> AsyncEngine:
    """
    Лениво создает engine для текущего event loop и URL БД.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
    """
    loop_id = _get_loop_id()
    
    settings = get_settings()
    if db_url is None:
        db_url = settings.database.url
    
    # Ключ кэша включает и loop_id и db_url
    cache_key = (loop_id, db_url)
    
    if cache_key in _engines:
        return _engines[cache_key]
    
    logger.debug(f"Создаем engine для event loop {loop_id}, db_url={db_url[:50]}...")

    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None

    if is_testing:
        # В тестах используем NullPool чтобы избежать проблем с event loops
        # Каждый тест имеет свой event loop, и соединения из пула могут оставаться
        # привязанными к закрытому loop, что вызывает RuntimeError
        # Теперь все операции используют session factory, что правильно
        engine = create_async_engine(
            db_url,
            echo=False,
            poolclass=NullPool,
        )
        logger.debug(f"Engine создан с NullPool для тестов (loop {loop_id})")
    else:
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=5,
            max_overflow=10,
        )
        logger.debug(f"Engine создан (loop {loop_id})")

    _engines[cache_key] = engine
    return engine


async def get_session_factory(db_url: Optional[str] = None) -> async_sessionmaker:
    """
    Лениво создает session factory для текущего event loop и URL БД.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
    """
    loop_id = _get_loop_id()
    
    settings = get_settings()
    if db_url is None:
        db_url = settings.database.url
    
    # Ключ кэша включает и loop_id и db_url
    cache_key = (loop_id, db_url)
    
    if cache_key in _session_factories:
        return _session_factories[cache_key]

    engine = await get_engine(db_url)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    _session_factories[cache_key] = session_factory
    logger.debug(f"Session factory создана (loop {loop_id}, db_url={db_url[:50]}...)")
    return session_factory


async def session(db_url: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Алиас для get_session_factory() - создает контекстный менеджер сессии.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
    
    Usage:
        async for s in session():
            await s.execute(...)
            break
    """
    session_factory = await get_session_factory(db_url)
    async with session_factory() as s:
        yield s


async def get_db(db_url: Optional[str] = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения сессии БД в FastAPI.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
    """
    session_factory = await get_session_factory(db_url)
    async with session_factory() as session:
        await session.rollback()
        yield session
        await session.close()


async def wait_for_db(max_retries: int = 30, retry_interval: int = 2, db_url: Optional[str] = None):
    """
    Ожидает готовности БД с повторными попытками.
    Если БД недоступна после всех попыток - бросает исключение.
    
    Args:
        max_retries: Максимальное количество попыток
        retry_interval: Интервал между попытками
        db_url: URL БД (если не указан, берется из settings.database.url)
    """
    for attempt in range(1, max_retries + 1):
        session_factory = await get_session_factory(db_url)
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
        logger.info(f"БД готова к работе (попытка {attempt}/{max_retries})")
        return

        if attempt < max_retries:
            logger.warning(
                f"БД не готова (попытка {attempt}/{max_retries}), "
                f"повтор через {retry_interval}с"
            )
            await asyncio.sleep(retry_interval)

    raise RuntimeError(f"БД недоступна после {max_retries} попыток")


async def create_tables(db_url: Optional[str] = None, table_names: Optional[List[str]] = None):
    """
    Создает таблицы в БД если их нет.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
        table_names: Список имен таблиц для создания (если None, создаются все)
    """
    # Явный импорт всех моделей для регистрации в Base.metadata
    from core.db.models import (
        Storage, Users, Variables, Tasks, Stores, AgentStates, OtelSpans
    )
    
    await wait_for_db(db_url=db_url)

    if table_names is None:
        tables_to_create = Base.metadata.tables
        logger.info(f"Создание всех таблиц из Base.metadata: {len(tables_to_create)}")
    else:
        tables_to_create = {name: Base.metadata.tables[name] for name in table_names if name in Base.metadata.tables}
        logger.info(f"Создание указанных таблиц: {list(tables_to_create.keys())}")

    for table_name in sorted(tables_to_create.keys()):
        logger.debug(f"  - {table_name}")

    session_factory = await get_session_factory(db_url)
    logger.info("Session factory получена для создания таблиц")
    
    async with session_factory() as session:
        logger.info("Вызываем Base.metadata.create_all...")
        async with session.begin():
            conn = await session.connection()
            if table_names is None:
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True)
                )
            else:
                tables_to_create = [Base.metadata.tables[name] for name in table_names if name in Base.metadata.tables]
                await conn.run_sync(
                    lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables_to_create, checkfirst=True)
                )
            logger.info("create_all завершен")
            
            # Проверяем, что таблицы действительно созданы
            if table_names:
                check_result = await conn.execute(
                    text("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = ANY(:table_names)
                    """),
                    {"table_names": table_names}
                )
                created_tables = [row[0] for row in check_result]
                missing_tables = set(table_names) - set(created_tables)
                if missing_tables:
                    logger.warning(f"⚠️  Таблицы не созданы: {missing_tables}")
                else:
                    logger.info(f"✅ Все таблицы созданы: {created_tables}")
    
    logger.info("Таблицы проверены/созданы")


async def drop_tables(db_url: Optional[str] = None):
    """
    Удаляет все таблицы.
    
    Args:
        db_url: URL БД (если не указан, берется из settings.database.url)
    """
    session_factory = await get_session_factory(db_url)
    async with session_factory() as session:
        async with session.begin():
            conn = await session.connection()
            await conn.run_sync(
                lambda sync_conn: Base.metadata.drop_all(sync_conn)
            )

    logger.info("Таблицы удалены")


async def close_db():
    """Закрывает соединения с БД для текущего event loop"""
    loop_id = _get_loop_id()

    engine = _engines.get(loop_id)
    if engine is not None:
        logger.info(f"Закрываем engine для event loop {loop_id}")
        await engine.dispose()
        logger.debug(f"Engine закрыт (loop {loop_id})")

        _engines.pop(loop_id, None)
        _session_factories.pop(loop_id, None)
        logger.info(f"Соединения с БД закрыты (loop {loop_id})")

