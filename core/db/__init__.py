"""
Database - работа с базой данных.

Включает:
- database.py - подключение к БД, engine, session factory
- storage.py - key-value storage с маршрутизацией по таблицам
- base_repository.py - базовый репозиторий для работы с моделями
- models.py - SQLAlchemy модели
- migrations.py - функции для запуска Alembic миграций
"""

from core.db.database import (
    get_engine,
    get_session_factory,
    session,
    get_db,
    wait_for_db,
    create_tables,
    close_db,
)
from core.db.storage import Storage
from core.db.base_repository import BaseRepository
from core.db.base_sql_repository import BaseSQLRepository
from core.db.migrations import run_migrations, run_migrations_async
from core.db.service_registry import register_service, get_unique_db_urls, get_service_by_name

__all__ = [
    "get_engine",
    "get_session_factory",
    "session",
    "get_db",
    "wait_for_db",
    "create_tables",
    "close_db",
    "run_migrations",
    "run_migrations_async",
    "register_service",
    "get_unique_db_urls",
    "get_service_by_name",
    "Storage",
    "BaseRepository",
    "BaseSQLRepository",
]

