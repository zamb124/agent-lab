"""
Alembic environment configuration.

Все модели наследуются от core.db.models.Base.
Alembic видит их через target_metadata = Base.metadata.

Сервисы регистрируются через core.db.service_registry.
При миграции итерируемся по всем уникальным URL БД.
"""

import asyncio
import logging
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Добавляем корень проекта в path для импортов
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Импортируем Base и core модели
# CRM-модели

# Импорт моделей - они автоматически регистрируются в Base.metadata и service_registry
# Модели сервиса Flows

# Sync-модели
from core.db.models import Base

# Теперь импортируем реестр после регистрации всех сервисов
from core.db.service_registry import get_unique_db_urls

# Push-модели (core)

config = context.config
logger = logging.getLogger("alembic.env")

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata содержит все таблицы из всех моделей
target_metadata = Base.metadata


def do_run_migrations(connection):
    """Выполняет миграции синхронно."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode - generates SQL script."""
    # В offline режиме берем первый URL из реестра
    db_urls = get_unique_db_urls()
    if not db_urls:
        raise RuntimeError("No database URLs registered")

    url = list(db_urls.keys())[0]

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode.

    Если connection передан через cfg.attributes["connection"] -
    используем его (для вызова из async контекста через run_migrations_async).
    Иначе итерируемся по всем уникальным БД через asyncio.run().
    """
    connectable = config.attributes.get("connection", None)

    if connectable is not None:
        # Connection уже передан - используем напрямую
        do_run_migrations(connectable)
    else:
        # Запускаем через asyncio.run (для CLI)
        asyncio.run(run_async_migrations())


async def run_async_migrations() -> None:
    """
    Применяет миграции ко всем уникальным БД.

    Итерируется по URL из service_registry и применяет
    одни и те же миграции к каждой уникальной БД.
    """
    db_urls = get_unique_db_urls()

    if not db_urls:
        logger.warning("No database URLs registered, skipping migrations")
        return

    for db_url, services in db_urls.items():
        logger.info(f"Migrating DB for services: {services}")

        engine = create_async_engine(db_url, poolclass=pool.NullPool)

        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)

        await engine.dispose()

        logger.info(f"Migrations completed for: {services}")


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
