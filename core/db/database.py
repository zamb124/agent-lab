"""
Настройка подключения к базе данных.

ВАЖНО: НЕ ИСПОЛЬЗУЕТ try-except для фолбэков.
Если БД недоступна - приложение падает (fail-fast).
"""

import asyncio
import os
import weakref
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import get_settings
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)


def _build_asyncpg_server_settings() -> dict[str, str]:
    """
    Собирает server_settings для asyncpg-драйвера: statement_timeout,
    lock_timeout, idle_in_transaction_session_timeout (значения 0 — пропускаются).

    PostgreSQL понимает значения как миллисекунды, переданные строкой.
    """
    db = get_settings().database
    server_settings: dict[str, str] = {}
    if db.statement_timeout_ms > 0:
        server_settings["statement_timeout"] = str(db.statement_timeout_ms)
    if db.lock_timeout_ms > 0:
        server_settings["lock_timeout"] = str(db.lock_timeout_ms)
    if db.idle_in_transaction_session_timeout_ms > 0:
        server_settings["idle_in_transaction_session_timeout"] = str(
            db.idle_in_transaction_session_timeout_ms
        )
    return server_settings


def _build_connect_args(db_url: str) -> JsonObject:
    """
    Готовит connect_args для create_async_engine.

    server_settings поддерживается только asyncpg-драйвером SQLAlchemy.
    Для других драйверов возвращает пустой словарь — таймауты придётся
    задавать на уровне БД (ALTER ROLE / SET) или через postgres URL options.
    """
    if "+asyncpg" not in db_url:
        return {}
    server_settings = _build_asyncpg_server_settings()
    if not server_settings:
        return {}
    return {"server_settings": server_settings}


def _require_shared_db_url() -> str:
    settings = get_settings()
    u = settings.database.shared_url
    if not u:
        raise ValueError("database.shared_url не задан")
    return u

_engines: weakref.WeakValueDictionary[tuple[int, str], AsyncEngine] = weakref.WeakValueDictionary()
_session_factories: weakref.WeakValueDictionary[
    tuple[int, str],
    async_sessionmaker[AsyncSession],
] = weakref.WeakValueDictionary()

def _get_loop_id() -> int:
    """Получает ID текущего event loop для кэширования"""
    loop = asyncio.get_running_loop()
    return id(loop)


async def get_engine(db_url: str | None = None) -> AsyncEngine:
    """
    Лениво создает engine для текущего event loop и URL БД.

    Аргументы:
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
    connect_args = _build_connect_args(db_url)

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
            connect_args=connect_args,
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
            connect_args=connect_args,
        )
        logger.debug(f"Engine создан (loop {loop_id})")

    _engines[cache_key] = engine
    return engine


async def get_session_factory(db_url: str | None = None) -> async_sessionmaker[AsyncSession]:
    """
    Лениво создает session factory для текущего event loop и URL БД.

    Аргументы:
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


async def session(db_url: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Алиас для get_session_factory() - создает контекстный менеджер сессии.

    Аргументы:
        db_url: URL БД (если не указан — shared_url)

    Использование:
        async for s in session():
            await s.execute(...)
            break
    """
    session_factory = await get_session_factory(db_url)
    async with session_factory() as s:
        yield s


async def get_db(db_url: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """
    Зависимость FastAPI для получения сессии БД.

    Аргументы:
        db_url: URL БД (если не указан — shared_url)
    """
    session_factory = await get_session_factory(db_url)
    async with session_factory() as session:
        await session.rollback()
        yield session
        await session.close()


async def wait_for_db(
    max_retries: int = 30,
    retry_interval: int = 2,
    db_url: str | None = None,
) -> None:
    """
    Ожидает готовности БД с повторными попытками.
    Если БД недоступна после всех попыток - бросает исключение.

    Аргументы:
        max_retries: Максимальное количество попыток
        retry_interval: Интервал между попытками
        db_url: URL БД (если не указан — shared_url)
    """
    if max_retries < 1:
        raise ValueError("max_retries должен быть >= 1")
    if retry_interval < 0:
        raise ValueError("retry_interval должен быть >= 0")

    for attempt in range(1, max_retries + 1):
        try:
            session_factory = await get_session_factory(db_url)
            async with session_factory() as session:
                _ = await session.execute(text("SELECT 1"))
            logger.info(f"БД готова к работе (попытка {attempt}/{max_retries})")
            return
        except SQLAlchemyError as exc:
            if attempt == max_retries:
                raise RuntimeError(f"БД недоступна после {max_retries} попыток") from exc
            logger.warning(
                f"БД не готова (попытка {attempt}/{max_retries}), "
                + f"повтор через {retry_interval}с: {exc}"
            )
            await asyncio.sleep(retry_interval)


async def close_db() -> None:
    """Закрывает соединения с БД для текущего event loop"""
    loop_id = _get_loop_id()

    keys = [key for key in list(_engines.keys()) if key[0] == loop_id]
    for key in keys:
        engine = _engines.get(key)
        if engine is None:
            continue
        logger.info(f"Закрываем engine для event loop {loop_id}")
        await engine.dispose()
        logger.debug(f"Engine закрыт (loop {loop_id})")

        _ = _engines.pop(key, None)
        _ = _session_factories.pop(key, None)
    if keys:
        logger.info(f"Соединения с БД закрыты (loop {loop_id})")
