"""REST-зеркало команд frontend/company_storages/*."""

from fastapi import APIRouter

from apps.frontend.di import Di
from apps.frontend.realtime.company_storage_operations import (
    CompanyStorageCreatePayload,
    CompanyStorageIdPayload,
    CompanyStorageListResult,
    CompanyStorageMigrationIdPayload,
    CompanyStorageMigrationStartPayload,
    CompanyStorageRotatePayload,
    CompanyStorageRoutePayload,
    StorageConnectionPayload,
    StorageProbeResult,
    op_company_storage_migrations_get,
    op_company_storage_migrations_start,
    op_company_storage_routes_set,
    op_company_storages_create,
    op_company_storages_delete,
    op_company_storages_list,
    op_company_storages_probe,
    op_company_storages_rotate,
)
from core.context import require_context
from core.files.object_storage import ObjectStorage
from core.files.storage_migration import StorageMigration
from core.files.storage_route import StorageRoute
from core.websocket import EmptyPayload

router = APIRouter(prefix="/api/company-storages", tags=["company-storages"])


@router.get("", response_model=CompanyStorageListResult)
async def list_company_storages(di: Di) -> CompanyStorageListResult:
    return await op_company_storages_list(
        EmptyPayload(), user=require_context().user, di=di
    )


@router.post("/probe", response_model=StorageProbeResult)
async def probe_company_storage(payload: StorageConnectionPayload, di: Di) -> StorageProbeResult:
    return await op_company_storages_probe(payload, user=require_context().user, di=di)


@router.post("", response_model=ObjectStorage)
async def create_company_storage(payload: CompanyStorageCreatePayload, di: Di) -> ObjectStorage:
    return await op_company_storages_create(payload, user=require_context().user, di=di)


@router.post("/rotate", response_model=ObjectStorage)
async def rotate_company_storage(payload: CompanyStorageRotatePayload, di: Di) -> ObjectStorage:
    return await op_company_storages_rotate(payload, user=require_context().user, di=di)


@router.post("/delete", response_model=CompanyStorageIdPayload)
async def delete_company_storage(payload: CompanyStorageIdPayload, di: Di) -> CompanyStorageIdPayload:
    return await op_company_storages_delete(payload, user=require_context().user, di=di)


@router.post("/routes", response_model=StorageRoute)
async def set_company_storage_route(payload: CompanyStorageRoutePayload, di: Di) -> StorageRoute:
    return await op_company_storage_routes_set(payload, user=require_context().user, di=di)


@router.post("/migrations", response_model=StorageMigration)
async def start_company_storage_migration(
    payload: CompanyStorageMigrationStartPayload, di: Di
) -> StorageMigration:
    return await op_company_storage_migrations_start(payload, user=require_context().user, di=di)


@router.post("/migrations/get", response_model=StorageMigration)
async def get_company_storage_migration(
    payload: CompanyStorageMigrationIdPayload, di: Di
) -> StorageMigration:
    return await op_company_storage_migrations_get(payload, user=require_context().user, di=di)
