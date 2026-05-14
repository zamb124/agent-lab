"""
Настройка подключения к базе данных.

ВАЖНО: НЕ ИСПОЛЬЗУЕТ try-except для фолбэков.
Если БД недоступна - приложение падает (fail-fast).
"""

import asyncio
import os
import weakref
from typing import AsyncGenerator, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)
def _require_shared_db_url() -> str:
    settings = get_settings()
    u = settings.database.shared_url
    if not u:
        raise ValueError("database.shared_url не задан")
    return u

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
        db_url: URL БД (если не указан — shared_url)
    """
    loop_id = _get_loop_id()

    if db_url is None:
        db_url = _require_shared_db_url()

    # Ключ кэша включает и loop_id и db_url
    cache_key = (loop_id, db_url)

    if cache_key in _engines:
        return _engines[cache_key]

    logger.debug(f"Создаем engine для event loop {loop_id}, db_url={db_url[:50]}...")

    is_testing = os.environ.get("PYTEST_CURRENT_TEST") is not None

    if is_testing:
        # В тестах используем маленький пул чтобы не превысить max_connections PostgreSQL
        # при параллельном запуске тестов (pytest-xdist)
        engine = create_async_engine(
            db_url,
            echo=False,
            pool_size=2,
            max_overflow=3,
            pool_pre_ping=True,
            pool_recycle=300,
        )
        logger.debug(f"Engine создан с маленьким пулом для тестов (loop {loop_id})")
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
        db_url: URL БД (если не указан — shared_url)
    """
    loop_id = _get_loop_id()

    if db_url is None:
        db_url = _require_shared_db_url()

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
        db_url: URL БД (если не указан — shared_url)

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
        db_url: URL БД (если не указан — shared_url)
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
        db_url: URL БД (если не указан — shared_url)
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

