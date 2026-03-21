"""Фикстуры для тестов Sync Service.

Использует платформенный паттерн: реальная БД, без моков.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from apps.sync.db.base import SyncDatabase
import apps.sync.db.models  # noqa: F401 — регистрация моделей в Base.metadata
from apps.sync.db.repositories.space_repository import SpaceRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.file_repository import FileRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository

from sqlalchemy import text


def _get_sync_test_db_url() -> str:
    """URL тестовой БД sync. Берётся из ENV или дефолт."""
    from tests.fixtures.test_database_env import TEST_DATABASE_ENV

    return os.environ.get("DATABASE__SYNC_URL", TEST_DATABASE_ENV["DATABASE__SYNC_URL"])


@pytest.fixture(scope="session")
def sync_db_url() -> str:
    return _get_sync_test_db_url()


@pytest_asyncio.fixture(scope="session")
async def sync_database(sync_db_url: str) -> AsyncIterator[SyncDatabase]:
    """Создаёт SyncDatabase и таблицы для тестовой сессии."""
    db = SyncDatabase(sync_db_url)
    await db.create_tables(drop_existing=True)
    yield db


@pytest_asyncio.fixture()
async def sync_db_clean(sync_database: SyncDatabase) -> None:
    """Очищает все sync таблицы перед каждым тестом через TRUNCATE CASCADE."""
    async with sync_database.session() as session:
        await session.execute(text(
            "TRUNCATE TABLE "
            "sync_message_files, sync_message_contents, sync_messages, "
            "sync_git_resource_refs, sync_files, sync_threads, "
            "sync_channel_members, sync_channels, sync_spaces "
            "RESTART IDENTITY CASCADE"
        ))
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
def file_repo(sync_database: SyncDatabase) -> FileRepository:
    return FileRepository(db=sync_database)


@pytest.fixture()
def git_ref_repo(sync_database: SyncDatabase) -> GitResourceRefRepository:
    return GitResourceRefRepository(db=sync_database)
