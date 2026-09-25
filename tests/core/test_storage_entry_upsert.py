"""Upsert строки storage по первичному ключу."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from oxyde import PoolSettings
from oxyde.db.pool import AsyncDatabase
from oxyde.db.registry import unregister_connection

from core.config import get_settings
from core.models.storage_entry import StorageEntry


@pytest_asyncio.fixture
async def single_connection_alias(unique_id: str) -> AsyncIterator[str]:
    """Алиас shared-базы ровно с одним соединением: запросы идут подряд по нему."""
    shared_url = get_settings().database.shared_url
    if shared_url is None or shared_url == "":
        raise RuntimeError("DATABASE__SHARED_URL is required")
    alias = f"storage_single_{unique_id}"
    database = AsyncDatabase(
        shared_url,
        name=alias,
        settings=PoolSettings(max_connections=1, acquire_timeout=5.0),
        auto_register=True,
        overwrite=True,
    )
    await database.connect()
    try:
        yield alias
    finally:
        await database.disconnect()
        unregister_connection(alias)


@pytest.mark.asyncio
async def test_upsert_by_key_updates_value_and_keeps_created_at(unique_id: str) -> None:
    key = f"orm-storage-{unique_id}"
    await StorageEntry.upsert_by_key(key, '{"n":1}', None, alias="shared")
    created = await StorageEntry.row(key, alias="shared", for_update=False)
    assert created is not None
    assert created.value == {"n": 1}

    await StorageEntry.upsert_by_key(key, '{"n":2}', None, alias="shared")
    updated = await StorageEntry.row(key, alias="shared", for_update=False)
    assert updated is not None
    assert updated.created_at == created.created_at
    assert updated.value == {"n": 2}
    assert updated.key == key


@pytest.mark.asyncio
async def test_upsert_with_expiry_after_upsert_without_expiry_on_one_connection(
    single_connection_alias: str,
    unique_id: str,
) -> None:
    without_expiry = f"orm-storage-no-ttl-{unique_id}"
    with_expiry = f"orm-storage-ttl-{unique_id}"
    expires = datetime.now(UTC) + timedelta(days=1)
    try:
        await StorageEntry.upsert_by_key(without_expiry, '{"n":1}', None, alias=single_connection_alias)
        await StorageEntry.upsert_by_key(with_expiry, '{"n":2}', expires, alias=single_connection_alias)

        stored = await StorageEntry.row(with_expiry, alias=single_connection_alias, for_update=False)
        assert stored is not None
        assert stored.expired_at is not None
        assert abs(stored.expired_at.replace(tzinfo=UTC) - expires) < timedelta(seconds=1)
    finally:
        _ = await StorageEntry.delete_key(without_expiry, alias=single_connection_alias)
        _ = await StorageEntry.delete_key(with_expiry, alias=single_connection_alias)


@pytest.mark.asyncio
async def test_upsert_rejects_naive_expiry(unique_id: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        await StorageEntry.upsert_by_key(
            f"orm-storage-naive-{unique_id}",
            '{"n":1}',
            datetime.now() + timedelta(days=1),
            alias="shared",
        )
