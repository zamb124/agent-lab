"""Фикстуры для тестов Sync Service.

Использует платформенный паттерн: реальная БД, без моков.
"""

from __future__ import annotations

import os

from tests.fixtures.test_database_env import TEST_DATABASE_ENV

for _k, _v in TEST_DATABASE_ENV.items():
    os.environ.setdefault(_k, _v)
os.environ.setdefault("S3__ENABLED", "true")
os.environ.setdefault("S3__DEFAULT_BUCKET", "test-bucket")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ENDPOINT_URL", "http://localhost:19002")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__ACCESS_KEY_ID", "minioadmin")
os.environ.setdefault("S3__BUCKETS__TEST-BUCKET__SECRET_ACCESS_KEY", "minioadmin")
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from apps.sync.db.base import SyncDatabase
import apps.sync.db.models  # noqa: F401 — регистрация моделей в Base.metadata
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.file_repository import SyncFileRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository

from sqlalchemy import text


def _get_sync_test_db_url() -> str:
    """URL тестовой БД sync. Берётся из ENV или дефолт."""
    return os.environ.get("DATABASE__SYNC_URL", TEST_DATABASE_ENV["DATABASE__SYNC_URL"])


@pytest.fixture(scope="session")
def sync_db_url() -> str:
    return _get_sync_test_db_url()


@pytest_asyncio.fixture(scope="session")
async def sync_database(sync_db_url: str) -> AsyncIterator[SyncDatabase]:
    """Создаёт SyncDatabase; схема только через Alembic (дерево migrations/sync)."""
    import core.config.base as config_base

    os.environ["DATABASE__SYNC_URL"] = sync_db_url
    config_base._settings_instance = None

    from apps.sync.container import reset_sync_container

    reset_sync_container()

    from core.db.migration_manifest import bootstrap_migration_registry
    from core.db.migrations import run_migrations_async

    bootstrap_migration_registry()
    await run_migrations_async(service="sync")

    db = SyncDatabase(sync_db_url)
    yield db


_SYNC_DELETE_ORDER = (
    # Дочерние таблицы первыми; без TRUNCATE — меньше AccessExclusiveLock и deadlock с xdist.
    "sync_call_links",
    "sync_call_participants",
    "sync_calls",
    "sync_message_files",
    "sync_message_contents",
    "sync_messages",
    "sync_threads",
    "sync_git_resource_refs",
    "sync_files",
    "sync_channel_members",
    "sync_channels",
    "sync_spaces",
)


@pytest_asyncio.fixture()
async def sync_db_clean(sync_database: SyncDatabase) -> None:
    """Полная очистка данных sync перед тестом: DELETE по порядку FK (без TRUNCATE)."""
    async with sync_database.session() as session:
        for table in _SYNC_DELETE_ORDER:
            await session.execute(text(f'DELETE FROM "{table}"'))
        seq_row = await session.execute(
            text("SELECT pg_get_serial_sequence('sync_message_contents', 'id')")
        )
        seq_name = seq_row.scalar_one_or_none()
        if seq_name:
            await session.execute(text(f"SELECT setval('{seq_name}', 1, false)"))
        await session.commit()


@pytest.fixture()
def unique_id() -> str:
    """Уникальный ID для изоляции тестовых данных."""
    return uuid.uuid4().hex[:12]


@pytest.fixture()
def company_id(unique_id: str) -> str:
    """company_id для изоляции тестов."""
    return f"test_company_{unique_id}"


@pytest.fixture()
def space_repo(sync_database: SyncDatabase) -> SpaceRepository:
    return SpaceRepository(db=sync_database)


@pytest.fixture()
def channel_repo(sync_database: SyncDatabase) -> ChannelRepository:
    return ChannelRepository(db=sync_database)


@pytest.fixture()
def thread_repo(sync_database: SyncDatabase) -> ThreadRepository:
    return ThreadRepository(db=sync_database)


@pytest.fixture()
def message_repo(sync_database: SyncDatabase) -> MessageRepository:
    return MessageRepository(db=sync_database)


@pytest.fixture()
def file_repo(sync_database: SyncDatabase) -> SyncFileRepository:
    return SyncFileRepository(db=sync_database)


@pytest.fixture()
def git_ref_repo(sync_database: SyncDatabase) -> GitResourceRefRepository:
    return GitResourceRefRepository(db=sync_database)


@pytest.fixture()
def call_repo(sync_database: SyncDatabase) -> CallRepository:
    return CallRepository(db=sync_database)


@pytest.fixture()
def sync_user_repository(sync_database: SyncDatabase):
    """UserRepository shared БД (как в dispatch_sync_command)."""
    from apps.sync.container import get_sync_container

    return get_sync_container().user_repository
