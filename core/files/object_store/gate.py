"""Единственный вход к байтам: политика, затем клиент хранилища записи."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import NoReturn

from core.authz.service import AuthzService
from core.errors.boundary import PlatformNotFoundError, PlatformUnavailableError
from core.files.create_spec import FileSourceKind
from core.files.models import FileRecord
from core.files.object_store.policy import authorize_file
from core.files.object_store.pool import client_for
from core.files.object_store.principals import FilePrincipal
from core.files.object_store.resolved import ResolvedStorage
from core.files.object_store.resolver import resolve_for_record, resolve_for_write
from core.files.object_store.s3_client import S3Client


@dataclass(frozen=True, slots=True)
class EgressTarget:
    storage_id: str
    bucket_name: str
    endpoint_url: str
    region_name: str
    access_key_id: str
    secret_access_key: str
    path_style: bool


_STORAGE_DOWN = frozenset(
    {
        "EndpointConnectionError",
        "ConnectTimeoutError",
        "ReadTimeoutError",
        "ConnectionClosedError",
        "ClientConnectorError",
        "ClientOSError",
        "ServerTimeoutError",
        "ServerDisconnectedError",
    }
)


def raise_storage_unavailable(exc: Exception) -> NoReturn:
    if type(exc).__name__ in _STORAGE_DOWN:
        raise PlatformUnavailableError("object storage is unavailable") from exc
    raise exc


class FileHandle:
    record: FileRecord
    _client: S3Client

    def __init__(self, record: FileRecord, client: S3Client) -> None:
        self.record = record
        self._client = client

    async def read_bytes(self) -> bytes:
        try:
            return await self._client.download_bytes(self.record.s3_key)
        except Exception as exc:
            raise_storage_unavailable(exc)

    async def stream(self, byte_range: str | None = None) -> AsyncIterator[bytes]:
        body = await self._client.open_object_body(self.record.s3_key, byte_range=byte_range)
        while True:
            chunk = await body.read(1024 * 1024)
            if not chunk:
                break
            yield chunk

    async def head(self) -> tuple[int, str]:
        meta = await self._client.get_object_metadata(self.record.s3_key)
        return meta.content_length, meta.content_type


class FileGate:
    _authz: AuthzService | None

    def __init__(self, authz: AuthzService | None = None) -> None:
        self._authz = authz

    async def open(self, file_id: str, principal: FilePrincipal) -> FileHandle:
        record = await FileRecord.get(file_id)
        if record is None:
            raise PlatformNotFoundError(f"file not found: {file_id}")
        return await self.open_record(record, principal)

    async def open_record(self, record: FileRecord, principal: FilePrincipal) -> FileHandle:
        await authorize_file(record, principal, self._authz)
        resolved = await resolve_for_record(record)
        client = await client_for(resolved)
        return FileHandle(record, client)

    async def client_for_write(self, company_id: str, source_kind: FileSourceKind) -> tuple[ResolvedStorage, S3Client]:
        resolved = await resolve_for_write(company_id, source_kind)
        return resolved, await client_for(resolved)

    async def client_for_storage_id(self, storage_id: str, *, record: FileRecord) -> S3Client:
        resolved = await resolve_for_record(record)
        if resolved.storage_id != storage_id:
            raise PlatformNotFoundError(f"file storage {record.storage_id} is not {storage_id}")
        return await client_for(resolved)

    async def egress_target(self, company_id: str, source_kind: FileSourceKind) -> EgressTarget:
        resolved = await resolve_for_write(company_id, source_kind)
        return EgressTarget(
            storage_id=resolved.storage_id,
            bucket_name=resolved.bucket_name,
            endpoint_url=resolved.endpoint_url,
            region_name=resolved.region_name,
            access_key_id=resolved.access_key_id,
            secret_access_key=resolved.secret_access_key,
            path_style=resolved.path_style,
        )
