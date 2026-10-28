"""Команды хранилищ компании."""

from __future__ import annotations

from pydantic import Field

from apps.frontend.di import Di
from apps.idle_worker.tasks.task_names import TASK_STORAGE_MIGRATION_TICK
from core.context import require_active_company
from core.errors.boundary import PlatformNotFoundError
from core.files.company_storage_service import CompanyStorageService
from core.files.create_spec import FileSourceKind
from core.files.events import STORAGE_MIGRATION_PROGRESSED
from core.files.object_storage import ObjectStorage
from core.files.storage_migration import StorageMigration
from core.files.storage_route import StorageRoute
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_company_admin
from core.tasks import enqueue
from core.websocket import EmptyPayload, raise_invalid

logger = get_logger(__name__)


class CompanyStorageListResult(StrictBaseModel):
    storages: list[ObjectStorage]
    routes: list[StorageRoute]


class StorageProbeResult(StrictBaseModel):
    ok: bool = True


class StorageConnectionPayload(StrictBaseModel):
    provider: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=1)
    region_name: str = Field(min_length=1)
    bucket_name: str = Field(min_length=1)
    path_style: bool = True
    access_key_id: str = Field(min_length=1)
    secret_access_key: str = Field(min_length=1)


class CompanyStorageCreatePayload(StorageConnectionPayload):
    name: str = Field(min_length=1)


class CompanyStorageIdPayload(StrictBaseModel):
    storage_id: str = Field(min_length=1)


class CompanyStorageRotatePayload(CompanyStorageIdPayload):
    access_key_id: str = Field(min_length=1)
    secret_access_key: str = Field(min_length=1)


class CompanyStorageRoutePayload(StrictBaseModel):
    storage_id: str = Field(min_length=1)
    source_kind: str | None = None


class CompanyStorageMigrationStartPayload(StrictBaseModel):
    source_storage_id: str = Field(min_length=1)
    target_storage_id: str = Field(min_length=1)


class CompanyStorageMigrationIdPayload(StrictBaseModel):
    storage_migration_id: str = Field(min_length=1)


def _service(di: Di) -> CompanyStorageService:
    return di.company_storage_service


def _kind(raw: str | None) -> FileSourceKind | None:
    if raw is None or raw == "" or raw == "default":
        return None
    try:
        return FileSourceKind(raw)
    except ValueError as exc:
        raise_invalid(exc)


async def op_company_storages_list(
    payload: EmptyPayload, *, user: User, di: Di
) -> CompanyStorageListResult:
    _ = payload, user
    scope = await require_company_admin(di.authz_service)
    company_id = scope.company_id
    return CompanyStorageListResult(
        storages=await ObjectStorage.list_by_created_at(company_id),
        routes=await StorageRoute.list_by_source_kind(company_id),
    )


async def op_company_storages_probe(
    payload: StorageConnectionPayload, *, user: User, di: Di
) -> StorageProbeResult:
    _ = user
    _ = await require_company_admin(di.authz_service)
    try:
        await _service(di).probe(
            provider=payload.provider,
            endpoint_url=payload.endpoint_url,
            region_name=payload.region_name,
            bucket_name=payload.bucket_name,
            path_style=payload.path_style,
            access_key_id=payload.access_key_id,
            secret_access_key=payload.secret_access_key,
        )
    except ValueError as exc:
        raise_invalid(exc)
    return StorageProbeResult()


async def op_company_storages_create(
    payload: CompanyStorageCreatePayload, *, user: User, di: Di
) -> ObjectStorage:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    try:
        return await _service(di).create(
            company_id,
            name=payload.name,
            provider=payload.provider,
            endpoint_url=payload.endpoint_url,
            region_name=payload.region_name,
            bucket_name=payload.bucket_name,
            path_style=payload.path_style,
            access_key_id=payload.access_key_id,
            secret_access_key=payload.secret_access_key,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_company_storages_rotate(
    payload: CompanyStorageRotatePayload, *, user: User, di: Di
) -> ObjectStorage:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    try:
        return await _service(di).rotate_credentials(
            company_id,
            payload.storage_id,
            access_key_id=payload.access_key_id,
            secret_access_key=payload.secret_access_key,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_company_storages_delete(
    payload: CompanyStorageIdPayload, *, user: User, di: Di
) -> CompanyStorageIdPayload:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    await _service(di).delete(company_id, payload.storage_id)
    return payload


async def op_company_storage_routes_set(
    payload: CompanyStorageRoutePayload, *, user: User, di: Di
) -> StorageRoute:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    return await _service(di).set_route(
        company_id,
        source_kind=_kind(payload.source_kind),
        storage_id=payload.storage_id,
    )


async def op_company_storage_migrations_start(
    payload: CompanyStorageMigrationStartPayload, *, user: User, di: Di
) -> StorageMigration:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    migration = await _service(di).start_migration(
        company_id,
        source_storage_id=payload.source_storage_id,
        target_storage_id=payload.target_storage_id,
    )
    _ = await enqueue(
        TASK_STORAGE_MIGRATION_TICK,
        storage_migration_id=migration.storage_migration_id,
    )
    logger.info(
        "company.storage.migration.started",
        storage_migration_id=migration.storage_migration_id,
        event_type=STORAGE_MIGRATION_PROGRESSED,
    )
    return migration


async def op_company_storage_migrations_get(
    payload: CompanyStorageMigrationIdPayload, *, user: User, di: Di
) -> StorageMigration:
    _ = user
    _ = await require_company_admin(di.authz_service)
    company_id = require_active_company().company_id
    row = await StorageMigration.get(payload.storage_migration_id)
    if row is None or row.company_id != company_id:
        raise PlatformNotFoundError("storage migration not found")
    return row
