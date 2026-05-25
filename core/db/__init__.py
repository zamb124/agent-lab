"""
Database - работа с базой данных.

Включает:
- database.py - подключение к БД, engine, session factory
- storage.py - key-value storage с маршрутизацией по таблицам
- base_repository.py - базовый репозиторий для работы с моделями
- models.py - SQLAlchemy модели
- migrations.py - функции для запуска Alembic миграций
"""

from core.db.base_repository import BaseRepository
from core.db.database import (
    close_db,
    get_db,
    get_engine,
    get_session_factory,
    session,
    wait_for_db,
)
from core.db.migrations import run_migrations, run_migrations_async
from core.db.service_registry import get_service_by_name, get_unique_db_urls, register_service
from core.db.storage import Storage
from core.db.utils import get_rowcount

__all__ = [
    "get_engine",
    "get_session_factory",
    "session",
    "get_db",
    "wait_for_db",
    "close_db",
    "run_migrations",
    "run_migrations_async",
    "register_service",
    "get_unique_db_urls",
    "get_service_by_name",
    "Storage",
    "BaseRepository",
    "get_rowcount",
]
