"""
Database - работа с базой данных.

Включает:
- database.py - подключение к БД, engine, session factory
- storage.py - key-value storage с маршрутизацией по таблицам
- base_repository.py - базовый репозиторий для работы с моделями
- models.py - SQLAlchemy модели
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

__all__ = [
    "get_engine",
    "get_session_factory",
    "session",
    "get_db",
    "wait_for_db",
    "create_tables",
    "close_db",
    "Storage",
    "BaseRepository",
]

