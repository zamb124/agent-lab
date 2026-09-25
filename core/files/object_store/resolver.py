"""Куда писать новый файл и откуда читать уже записанный."""

from __future__ import annotations

from core.errors.boundary import PlatformConflictError, PlatformUnavailableError
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.object_storage import PLATFORM_STORAGE_ID, ObjectStorage, ObjectStorageState
from core.files.object_store.resolved import (
    ResolvedStorage,
    resolve_company_storage,
    resolve_platform_storage,
)
from core.files.storage_route import StorageRoute

_WRITABLE = frozenset({ObjectStorageState.ACTIVE.value})
_READABLE = frozenset({ObjectStorageState.ACTIVE.value, ObjectStorageState.DRAINING.value})


async def _company_row(storage_id: str, *, readable: bool) -> ObjectStorage:
    row = await ObjectStorage.get(storage_id)
    if row is None:
        raise PlatformUnavailableError(f"object storage {storage_id} is missing")
    allowed = _READABLE if readable else _WRITABLE
    if row.state not in allowed:
        raise PlatformConflictError(f"object storage {storage_id} is {row.state}")
    return row


async def resolve_for_write(company_id: str, source_kind: FileSourceKind) -> ResolvedStorage:
    if company_id == "" or source_kind is FileSourceKind.PLATFORM_AUXILIARY:
        return resolve_platform_storage()
    specific = await StorageRoute.for_kind(company_id, source_kind)
    if specific is not None:
        if specific.storage_id == PLATFORM_STORAGE_ID:
            return resolve_platform_storage()
        return resolve_company_storage(await _company_row(specific.storage_id, readable=False))
    default = await StorageRoute.for_kind(company_id, None)
    if default is not None:
        if default.storage_id == PLATFORM_STORAGE_ID:
            return resolve_platform_storage()
        return resolve_company_storage(await _company_row(default.storage_id, readable=False))
    return resolve_platform_storage()


async def resolve_storage_id(storage_id: str) -> ResolvedStorage:
    if storage_id == PLATFORM_STORAGE_ID:
        return resolve_platform_storage()
    return resolve_company_storage(await _company_row(storage_id, readable=True))


async def resolve_for_record(record: FileRecord) -> ResolvedStorage:
    if record.storage_id == PLATFORM_STORAGE_ID:
        return resolve_platform_storage()
    return resolve_company_storage(await _company_row(record.storage_id, readable=True))
