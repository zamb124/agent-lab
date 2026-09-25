"""Подключения S3 компании: проверка, маршрут по роду файла, перенос."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.object_storage import (
    PLATFORM_STORAGE_ID,
    ObjectStorage,
    ObjectStorageState,
)
from core.files.object_store.probe import probe_storage
from core.files.object_store.resolved import ResolvedStorage, resolve_company_storage
from core.files.object_store.ssrf import assert_company_endpoint
from core.files.storage_migration import StorageMigration, StorageMigrationState
from core.files.storage_route import StorageRoute, storage_route_id
from core.secrets.crypto import encrypt_secret


class CompanyStorageService:
    async def probe(
        self,
        *,
        provider: str,
        endpoint_url: str,
        region_name: str,
        bucket_name: str,
        path_style: bool,
        access_key_id: str,
        secret_access_key: str,
    ) -> None:
        assert_company_endpoint(endpoint_url)
        try:
            await probe_storage(
                resolved_for_probe(
                    endpoint_url=endpoint_url,
                    region_name=region_name,
                    bucket_name=bucket_name,
                    path_style=path_style,
                    access_key_id=access_key_id,
                    secret_access_key=secret_access_key,
                    provider=provider,
                )
            )
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("storage probe failed") from exc

    async def create(
        self,
        company_id: str,
        *,
        name: str,
        provider: str,
        endpoint_url: str,
        region_name: str,
        bucket_name: str,
        path_style: bool,
        access_key_id: str,
        secret_access_key: str,
    ) -> ObjectStorage:
        assert_company_endpoint(endpoint_url)
        storage_id = f"storage_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        row = ObjectStorage(
            storage_id=storage_id,
            company_id=company_id,
            name=name,
            provider=provider,
            endpoint_url=endpoint_url,
            region_name=region_name,
            bucket_name=bucket_name,
            path_style=path_style,
            access_key_id=access_key_id,
            secret_access_key_encrypted=encrypt_secret(secret_access_key),
            credentials_version=1,
            state=ObjectStorageState.VERIFYING.value,
            created_at=now,
            updated_at=now,
        )
        _ = await ObjectStorage.set(row)
        try:
            await probe_storage(resolve_company_storage(row))
        except Exception as exc:
            _ = await ObjectStorage.delete_by_id(storage_id)
            raise ValueError("storage probe failed") from exc
        row.state = ObjectStorageState.ACTIVE.value
        row.verified_at = datetime.now(timezone.utc)
        row.updated_at = row.verified_at
        _ = await ObjectStorage.set(row)
        return row

    async def rotate_credentials(
        self,
        company_id: str,
        storage_id: str,
        *,
        access_key_id: str,
        secret_access_key: str,
    ) -> ObjectStorage:
        row = await self._owned(company_id, storage_id)
        if row.state != ObjectStorageState.ACTIVE.value:
            raise PlatformConflictError(f"object storage {storage_id} is {row.state}")
        candidate = row.model_copy(
            update={
                "access_key_id": access_key_id,
                "secret_access_key_encrypted": encrypt_secret(secret_access_key),
                "credentials_version": row.credentials_version + 1,
            }
        )
        await probe_storage(resolve_company_storage(candidate))
        candidate.verified_at = datetime.now(timezone.utc)
        candidate.updated_at = candidate.verified_at
        _ = await ObjectStorage.set(candidate)
        return candidate

    async def delete(self, company_id: str, storage_id: str) -> None:
        row = await self._owned(company_id, storage_id)
        alive = await FileRecord.count_for_storage(storage_id)
        if alive > 0:
            raise PlatformConflictError("object storage still has files")
        routes = await StorageRoute.list_for_storage(storage_id)
        if routes:
            raise PlatformConflictError("object storage still has routes")
        running = await StorageMigration.running_for_source(storage_id)
        if running is not None:
            raise PlatformConflictError("object storage has a running migration")
        if row.state == ObjectStorageState.ACTIVE.value:
            row.state = ObjectStorageState.DRAINING.value
        if row.state != ObjectStorageState.RETIRED.value:
            row.state = ObjectStorageState.RETIRED.value
        row.updated_at = datetime.now(timezone.utc)
        _ = await ObjectStorage.set(row)
        _ = await ObjectStorage.delete_by_id(storage_id)

    async def set_route(
        self,
        company_id: str,
        *,
        source_kind: FileSourceKind | None,
        storage_id: str,
    ) -> StorageRoute:
        if storage_id != PLATFORM_STORAGE_ID:
            target = await self._owned(company_id, storage_id)
            if target.state != ObjectStorageState.ACTIVE.value:
                raise PlatformConflictError(f"object storage {storage_id} is {target.state}")
        now = datetime.now(timezone.utc)
        route = StorageRoute(
            storage_route_id=storage_route_id(company_id, source_kind),
            company_id=company_id,
            source_kind=source_kind.value if source_kind is not None else "default",
            storage_id=storage_id,
            updated_at=now,
        )
        _ = await StorageRoute.set(route)
        return route

    async def start_migration(
        self,
        company_id: str,
        *,
        source_storage_id: str,
        target_storage_id: str,
    ) -> StorageMigration:
        if source_storage_id == target_storage_id:
            raise PlatformConflictError("migration source and target are the same storage")
        source = await self._owned(company_id, source_storage_id)
        if target_storage_id != PLATFORM_STORAGE_ID:
            target = await self._owned(company_id, target_storage_id)
            if target.state != ObjectStorageState.ACTIVE.value:
                raise PlatformConflictError(f"object storage {target_storage_id} is {target.state}")
        if source.state not in (ObjectStorageState.ACTIVE.value, ObjectStorageState.DRAINING.value):
            raise PlatformConflictError(f"object storage {source_storage_id} is {source.state}")
        existing = await StorageMigration.running_for_source(source_storage_id)
        if existing is not None:
            raise PlatformConflictError("a migration from this storage is already running")
        source.state = ObjectStorageState.DRAINING.value
        source.updated_at = datetime.now(timezone.utc)
        _ = await ObjectStorage.set(source)
        migration = StorageMigration(
            storage_migration_id=f"mig_{uuid.uuid4().hex[:16]}",
            company_id=company_id,
            source_storage_id=source_storage_id,
            target_storage_id=target_storage_id,
            state=StorageMigrationState.RUNNING.value,
            files_total=await FileRecord.count_for_storage(source_storage_id),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        _ = await StorageMigration.set(migration)
        return migration

    async def _owned(self, company_id: str, storage_id: str) -> ObjectStorage:
        if storage_id == PLATFORM_STORAGE_ID:
            raise PlatformConflictError("platform storage is not a company row")
        row = await ObjectStorage.get(storage_id)
        if row is None or row.company_id != company_id:
            raise PlatformNotFoundError(f"object storage not found: {storage_id}")
        return row


def resolved_for_probe(
    *,
    endpoint_url: str,
    region_name: str,
    bucket_name: str,
    path_style: bool,
    access_key_id: str,
    secret_access_key: str,
    provider: str,
) -> ResolvedStorage:
    return ResolvedStorage(
        storage_id="probe",
        endpoint_url=endpoint_url,
        region_name=region_name,
        bucket_name=bucket_name,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        provider=provider,
        path_style=path_style,
        credentials_version=0,
    )
