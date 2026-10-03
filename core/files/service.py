"""Единый сервис работы с файлами платформы."""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from pathlib import Path

from core.authz.service import AuthzService
from core.config import get_settings
from core.context import require_active_company, require_context, resolve_namespace_or_raise
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE, normalize_data_table_filename
from core.documents.placement import DocumentPlacement
from core.documents.tree_service import DocumentTreeService, PlaceResult
from core.errors.boundary import PlatformConflictError, PlatformNotFoundError
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef, stored_file_ref
from core.files.models import FileRecord
from core.files.object_key import object_key
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import FilePrincipal
from core.files.retention import FileRetentionKind
from core.files.retention_promote import promote_file_retention_record
from core.files.storage import FileStorage, retention_fields_from_spec
from core.files.types import FileCategory, ext_to_category
from core.files.urls import normalize_files_route_segment
from core.types import JsonObject

RagIndexHook = Callable[[str, str, JsonObject | None], Awaitable[None]]


def _source_kind_metadata_value(source_kind: FileSourceKind | str) -> str:
    """StrictBaseModel(use_enum_values=True) хранит source_kind как str — нормализуем в wire value."""
    return FileSourceKind(source_kind).value


class FilesService:
    def __init__(
        self,
        *,
        files_route_segment: str,
        tree: DocumentTreeService,
        rag_index_hook: RagIndexHook | None = None,
    ) -> None:
        self._storage: FileStorage = FileStorage()
        self._files_route_segment: str = normalize_files_route_segment(files_route_segment)
        self._tree: DocumentTreeService = tree
        self._rag_index_hook: RagIndexHook | None = rag_index_hook

    def _resolve_route_segment(self, route_segment: str | None) -> str:
        if route_segment is not None:
            return normalize_files_route_segment(route_segment)
        return self._files_route_segment

    async def create(
        self,
        spec: FileCreateSpec,
        data: bytes,
        *,
        original_name: str,
        content_type: str,
        content_sha256_hex: str | None = None,
        route_segment: str | None = None,
    ) -> FileRecord:
        settings = get_settings()
        if not settings.s3.enabled:
            raise RuntimeError("S3 is not configured")

        context = require_context()
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("active company is required for file create")
        user_id = context.user.user_id

        effective_name = original_name
        effective_type = content_type
        category = ext_to_category(Path(original_name).suffix.lower())
        if category is FileCategory.DATA_TABLE:
            effective_name = normalize_data_table_filename(original_name)
            effective_type = DATA_TABLE_CONTENT_TYPE

        retention_kind, ttl_seconds = retention_fields_from_spec(spec.retention)
        post_create = spec.post_create if spec.post_create is not None else FilePostCreate()
        is_public = post_create.is_public

        metadata: JsonObject = dict(spec.metadata) if spec.metadata else {}
        metadata["source_kind"] = _source_kind_metadata_value(spec.source_kind)
        metadata["source_ref"] = spec.source_ref.model_dump(exclude_none=True)

        file_record = await self._storage.upload_bytes(
            data=data,
            original_name=effective_name,
            content_type=effective_type,
            uploaded_by=user_id,
            company_id=company_id,
            is_public=is_public,
            retention_kind=retention_kind,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
            tags=spec.tags,
            content_sha256_hex=content_sha256_hex,
            route_segment=self._resolve_route_segment(route_segment),
            source_kind=FileSourceKind(spec.source_kind),
        )

        await self._run_post_create(file_record, spec, post_create)
        return await self._bind_after_create(file_record, spec, title=effective_name)

    async def register_s3(
        self,
        spec: FileCreateSpec,
        *,
        s3_key: str,
        storage_id: str,
        original_name: str,
        content_type: str,
        file_size: int,
        existing_file_id: str | None = None,
        content_sha256_hex: str | None = None,
        route_segment: str | None = None,
    ) -> FileRecord:
        settings = get_settings()
        if not settings.s3.enabled:
            raise RuntimeError("S3 is not configured")

        context = require_context()
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("active company is required for register_s3")
        user_id = context.user.user_id

        retention_kind, ttl_seconds = retention_fields_from_spec(spec.retention)
        post_create = spec.post_create if spec.post_create is not None else FilePostCreate()
        metadata: JsonObject = dict(spec.metadata) if spec.metadata else {}
        metadata["source_kind"] = _source_kind_metadata_value(spec.source_kind)
        metadata["source_ref"] = spec.source_ref.model_dump(exclude_none=True)

        file_record = await self._storage.register_s3_object(
            s3_key=s3_key,
            storage_id=storage_id,
            original_name=original_name,
            content_type=content_type,
            file_size=file_size,
            uploaded_by=user_id,
            company_id=company_id,
            is_public=post_create.is_public,
            retention_kind=retention_kind,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
            tags=spec.tags,
            existing_file_id=existing_file_id,
            content_sha256_hex=content_sha256_hex,
            route_segment=self._resolve_route_segment(route_segment),
        )
        await self._run_post_create(file_record, spec, post_create)
        return await self._bind_after_create(file_record, spec, title=original_name)

    async def get(self, file_id: str) -> FileRecord:
        record = await self._storage.get(file_id)
        if record is None:
            raise ValueError(f"file not found: {file_id}")
        return record

    async def get_optional(self, file_id: str) -> FileRecord | None:
        return await self._storage.get(file_id)

    async def require_stored_file_ref(self, file_id: str) -> FileRef:
        record = await self.get_optional(file_id)
        if record is None:
            raise PlatformNotFoundError(f"File {file_id!r} not found.")
        return stored_file_ref(record)

    async def place(self, file_id: str, placement: DocumentPlacement) -> PlaceResult:
        record = await self.get(file_id)
        kind = FileSourceKind(record.source_kind) if record.source_kind else FileSourceKind.OFFICE_DOCUMENT
        return await self._tree.place(
            record,
            source_kind=kind,
            source_ref=FileSourceRef(),
            placement=placement,
            namespace=resolve_namespace_or_raise(),
            user_id=record.uploaded_by or "",
        )

    async def read_bytes(
        self,
        file_record: FileRecord,
        principal: FilePrincipal,
        *,
        authz: AuthzService | None = None,
    ) -> bytes:
        handle = await FileGate(authz).open_record(file_record, principal)
        return await handle.read_bytes()

    async def delete(self, file_id: str) -> bool:
        return await self._storage.delete(file_id)

    async def save(self, file_record: FileRecord) -> FileRecord:
        return await self._storage.save(file_record)

    async def save_file_size_checksum(
        self,
        file_record: FileRecord,
        *,
        file_size: int,
        checksum: str,
    ) -> FileRecord:
        updated = file_record.model_copy(
            update={"file_size": file_size, "checksum": checksum},
        )
        return await self.save(updated)

    async def replace_content(
        self,
        record: FileRecord,
        data: bytes,
        *,
        content_type: str,
        expected_checksum: str | None,
    ) -> FileRecord:
        if expected_checksum is not None and record.checksum != expected_checksum:
            raise PlatformConflictError("file checksum mismatch")
        if record.company_id is None or record.company_id == "":
            raise ValueError("file has no company")
        digest = hashlib.sha256(data).hexdigest()
        new_key = object_key(record.company_id, record.file_id, digest[:16], record.original_name)
        s3 = await FileGate().client_for_storage_id(record.storage_id, record=record)
        _ = await s3.upload_bytes(
            data=data,
            key=new_key,
            content_type=content_type,
            public=record.is_public,
        )
        claimed = await FileRecord.claim_content_replace(
            record.file_id,
            expected_checksum=record.checksum,
            s3_key=new_key,
            file_size=len(data),
            checksum=digest,
        )
        if not claimed:
            _ = await s3.delete_file(new_key)
            raise PlatformConflictError("file checksum mismatch")
        if new_key != record.s3_key:
            _ = await s3.delete_file(record.s3_key)
        return await self.get(record.file_id)

    async def promote_retention(
        self,
        file_id: str,
        *,
        retention_kind: FileRetentionKind,
        source_kind: FileSourceKind | None = None,
    ) -> FileRecord:
        record = await self.get(file_id)
        promoted, changed = promote_file_retention_record(
            record,
            retention_kind=retention_kind,
            source_kind=source_kind,
        )
        if not changed:
            return record
        return await self.save(promoted)

    async def _bind_after_create(
        self,
        file_record: FileRecord,
        spec: FileCreateSpec,
        *,
        title: str,
    ) -> FileRecord:
        _ = title
        try:
            placed = await self._tree.place(
                file_record,
                source_kind=FileSourceKind(spec.source_kind),
                source_ref=spec.source_ref,
                placement=spec.placement,
                namespace=resolve_namespace_or_raise(),
                user_id=file_record.uploaded_by or "",
            )
        except Exception as bind_error:
            _ = await self.delete(file_record.file_id)
            raise bind_error
        if placed.record.file_id != file_record.file_id:
            _ = await self.delete(file_record.file_id)
        return placed.record

    async def _run_post_create(
        self,
        file_record: FileRecord,
        spec: FileCreateSpec,
        post_create: FilePostCreate,
    ) -> None:
        _ = spec
        if self._rag_index_hook is None:
            return
        namespace_id = post_create.rag_index_namespace
        if namespace_id is None:
            return
        await self._rag_index_hook(file_record.file_id, namespace_id, post_create.rag_metadata)
