"""Перенос файлов компании между хранилищами. Повтор батча безопасен."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID, ObjectStorage, ObjectStorageState
from core.files.object_store.pool import client_for
from core.files.object_store.resolved import resolve_company_storage, resolve_platform_storage
from core.files.storage_migration import StorageMigration, StorageMigrationState
from core.files.storage_route import StorageRoute

_BATCH = 20


async def _target_resolved(storage_id: str):
    if storage_id == PLATFORM_STORAGE_ID:
        return resolve_platform_storage()
    row = await ObjectStorage.get(storage_id)
    if row is None or row.state != ObjectStorageState.ACTIVE.value:
        raise PlatformUnavailableError(f"migration target {storage_id} is not active")
    return resolve_company_storage(row)


async def _move_file(record: FileRecord, migration: StorageMigration) -> int:
    source = await client_for(
        resolve_company_storage(await ObjectStorage.require(migration.source_storage_id))
    )
    data = await source.download_bytes(record.s3_key)
    digest = hashlib.sha256(data).hexdigest()
    target = await client_for(await _target_resolved(migration.target_storage_id))
    _ = await target.upload_bytes(
        data=data,
        key=record.s3_key,
        content_type=record.content_type,
    )
    copied = await target.download_bytes(record.s3_key)
    if hashlib.sha256(copied).hexdigest() != digest or len(copied) != len(data):
        raise ValueError(f"checksum mismatch while moving {record.file_id}")
    claimed = await FileRecord.claim_storage_move(
        record.file_id,
        source_storage_id=migration.source_storage_id,
        target_storage_id=migration.target_storage_id,
        s3_key=record.s3_key,
    )
    if claimed:
        _ = await source.delete_file(record.s3_key)
    return len(data)


async def run_storage_migration_batch(storage_migration_id: str) -> StorageMigration:
    migration = await StorageMigration.get(storage_migration_id)
    if migration is None:
        raise PlatformNotFoundError(f"storage migration not found: {storage_migration_id}")
    if migration.state != StorageMigrationState.RUNNING.value:
        return migration
    rows = await FileRecord.list_for_storage_after(
        migration.source_storage_id,
        after_file_id=None,
        limit=_BATCH,
    )
    moved_bytes = 0
    try:
        for record in rows:
            moved_bytes += await _move_file(record, migration)
    except Exception as exc:
        migration.last_error = str(exc)
        migration.state = StorageMigrationState.FAILED.value
        migration.updated_at = datetime.now(timezone.utc)
        _ = await StorageMigration.set(migration)
        raise
    remaining = await FileRecord.count_for_storage(migration.source_storage_id)
    migration.files_moved = migration.files_total - remaining
    migration.bytes_moved += moved_bytes
    migration.cursor = rows[-1].file_id if rows else migration.cursor
    migration.last_error = None
    migration.updated_at = datetime.now(timezone.utc)
    if remaining == 0:
        migration.state = StorageMigrationState.COMPLETED.value
        routes = await StorageRoute.list_for_storage(migration.source_storage_id)
        if not routes:
            source = await ObjectStorage.get(migration.source_storage_id)
            if source is not None:
                source.state = ObjectStorageState.RETIRED.value
                source.updated_at = migration.updated_at
                _ = await ObjectStorage.set(source)
    _ = await StorageMigration.set(migration)
    return migration
