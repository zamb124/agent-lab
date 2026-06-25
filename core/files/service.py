"""Единый сервис работы с файлами платформы."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from core.config import get_settings
from core.context import require_active_company, require_context
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.create_spec import FileCreateSpec, FilePostCreate
from core.files.file_repository import FileRepository
from core.files.models import FileRecord
from core.files.storage import FileStorage, retention_fields_from_spec
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

RagIndexHook = Callable[[str, str, JsonObject | None], Awaitable[None]]
DocsBindHook = Callable[[DocsPlacement], Awaitable[DocsBindResult]]


class FilesService:
    def __init__(
        self,
        file_repository: FileRepository,
        *,
        rag_index_hook: RagIndexHook | None = None,
        docs_bind_hook: DocsBindHook | None = None,
    ) -> None:
        self._storage: FileStorage = FileStorage(file_repository=file_repository)
        self._rag_index_hook: RagIndexHook | None = rag_index_hook
        self._docs_bind_hook: DocsBindHook | None = docs_bind_hook

    async def create(
        self,
        spec: FileCreateSpec,
        data: bytes,
        *,
        original_name: str,
        content_type: str,
        content_sha256_hex: str | None = None,
    ) -> FileRecord:
        settings = get_settings()
        if not settings.s3.enabled or not settings.s3.default_bucket:
            raise RuntimeError("S3 is not configured")

        context = require_context()
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("active company is required for file create")
        user_id = context.user.user_id

        retention_kind, ttl_seconds = retention_fields_from_spec(spec.retention)
        post_create = spec.post_create if spec.post_create is not None else FilePostCreate()
        is_public = post_create.is_public

        metadata: JsonObject = dict(spec.metadata) if spec.metadata else {}
        metadata["source_kind"] = spec.source_kind

        file_record = await self._storage.upload_bytes(
            data=data,
            original_name=original_name,
            content_type=content_type,
            uploaded_by=user_id,
            company_id=company_id,
            is_public=is_public,
            retention_kind=retention_kind,
            ttl_seconds=ttl_seconds,
            metadata=metadata,
            tags=spec.tags,
            content_sha256_hex=content_sha256_hex,
        )

        await self._run_post_create(file_record, spec, post_create)
        if spec.placement is not None:
            placement = spec.placement.model_copy(update={"file_id": file_record.file_id})
            _ = await self.bind(file_record.file_id, placement)
        return file_record

    async def register_s3(
        self,
        spec: FileCreateSpec,
        *,
        s3_key: str,
        s3_bucket: str,
        original_name: str,
        content_type: str,
        file_size: int,
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
        metadata["source_kind"] = spec.source_kind

        file_record = await self._storage.register_s3_object(
            s3_key=s3_key,
            s3_bucket=s3_bucket,
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
        )
        await self._run_post_create(file_record, spec, post_create)
        if spec.placement is not None:
            placement = spec.placement.model_copy(update={"file_id": file_record.file_id})
            _ = await self.bind(file_record.file_id, placement)
        return file_record

    async def get(self, file_id: str) -> FileRecord:
        record = await self._storage.get(file_id)
        if record is None:
            raise ValueError(f"file not found: {file_id}")
        return record

    async def get_optional(self, file_id: str) -> FileRecord | None:
        return await self._storage.get(file_id)

    async def bind(self, file_id: str, placement: DocsPlacement) -> DocsBindResult:
        if self._docs_bind_hook is None:
            raise RuntimeError("docs bind is not configured for this FilesService")
        if placement.file_id != file_id:
            raise ValueError("placement.file_id must match file_id argument")
        _ = await self.get(file_id)
        return await self._docs_bind_hook(placement)

    async def delete(self, file_id: str) -> bool:
        return await self._storage.delete(file_id)

    async def save(self, file_record: FileRecord) -> FileRecord:
        return await self._storage.save(file_record)

    async def _run_post_create(
        self,
        file_record: FileRecord,
        spec: FileCreateSpec,
        post_create: FilePostCreate,
    ) -> None:
        if self._rag_index_hook is None:
            return
        namespace_id = post_create.rag_index_namespace
        if namespace_id is None and spec.source_kind == "rag_document":
            namespace_id = spec.source_ref.namespace_id
        if namespace_id is None:
            return
        await self._rag_index_hook(file_record.file_id, namespace_id, post_create.rag_metadata)
