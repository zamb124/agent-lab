"""Database: Storage, реестр сервисов и запуск миграций."""

from core.db.migrations import run_migrations_async
from core.db.service_registry import get_service_by_name, get_unique_db_urls, register_service
from core.db.storage import Storage

__all__ = [
    "run_migrations_async",
    "register_service",
    "get_unique_db_urls",
    "get_service_by_name",
    "Storage",
]
