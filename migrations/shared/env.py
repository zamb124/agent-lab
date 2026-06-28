"""
Alembic env для shared БД.

Управляет таблицами: storage, users, usage, namespaces, push_subscriptions.
"""

import asyncio
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from core.db.models.platform import (  # noqa: F401 — регистрируют таблицы в Base.metadata
    ApiKeyRecord,
    Base,
    CalendarEventRecord,
    CalendarIntegrationRecord,
    IntegrationCredentialRecord,
    Namespaces,
    PlatformShortLink,
    PushSubscription,
    SchedulerTaskRecord,
    Storage,
    Usage,
    Users,
)

config = context.config
logger = logging.getLogger("alembic.env")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

MANAGED_TABLES = {
    "storage", "users", "usage",
    "namespaces", "push_subscriptions",
    "calendar_events", "calendar_integrations", "integration_credentials",
    "scheduler_tasks", "platform_short_links", "api_keys",
}


def include_object(obj, name, type_, reflected, compare_to):
    if type_ == "table":
        return name in MANAGED_TABLES
    return True


def _get_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from core.config import get_settings
    settings = get_settings()
    if not settings.database.shared_url:
        raise ValueError("DATABASE__SHARED_URL не настроен")
    return settings.database.shared_url


def do_run_migrations(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection", None)
    if connectable is not None:
        do_run_migrations(connectable)
    else:
        asyncio.run(_run_async())


async def _run_async() -> None:
    engine = create_async_engine(_get_url(), poolclass=pool.NullPool)
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
