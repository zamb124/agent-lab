"""Единый сервис работы с файлами платформы."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import require_active_company, require_context
from core.data_tables.models import DATA_TABLE_CONTENT_TYPE, normalize_data_table_filename
from core.documents.placement import DocsBindResult, DocsPlacement
from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind
from core.files.file_repository import FileRepository
from core.files.models import FileRecord
from core.files.registry import default_docs_placement
from core.files.retention import FileRetentionKind
from core.files.retention_promote import promote_file_retention_record
from core.files.storage import FileStorage, retention_fields_from_spec
from core.files.types import FileCategory, ext_to_category
from core.files.urls import normalize_files_route_segment
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

RagIndexHook = Callable[[str, str, JsonObject | None], Awaitable[None]]
DocsBindHook = Callable[[DocsPlacement], Awaitable[DocsBindResult]]


def _source_kind_metadata_value(source_kind: FileSourceKind | str) -> str:
    """StrictBaseModel(use_enum_values=True) хранит source_kind как str — нормализуем в wire value."""
    return FileSourceKind(source_kind).value


class FilesService:
    def __init__(
        self,
        file_repository: FileRepository,
        *,
        files_route_segment: str,
        rag_index_hook: RagIndexHook | None = None,
        docs_bind_hook: DocsBindHook | None = None,
    ) -> None:
        self._storage: FileStorage = FileStorage(file_repository=file_repository)
        self._files_route_segment: str = normalize_files_route_segment(files_route_segment)
        self._rag_index_hook: RagIndexHook | None = rag_index_hook
        self._docs_bind_hook: DocsBindHook | None = docs_bind_hook

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
        if not settings.s3.enabled or not settings.s3.default_bucket:
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
        )

        await self._run_post_create(file_record, spec, post_create)
        await self._bind_after_create(file_record, spec, title=effective_name)
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
            existing_file_id=existing_file_id,
            content_sha256_hex=content_sha256_hex,
            route_segment=self._resolve_route_segment(route_segment),
        )
        await self._run_post_create(file_record, spec, post_create)
        await self._bind_after_create(file_record, spec, title=original_name)
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
    ) -> None:
        placement = spec.placement
        if placement is None:
            placement = default_docs_placement(
                spec.source_kind,
                spec.source_ref,
                title=title,
            )
        if placement is None:
            return
        bound = placement.model_copy(update={"file_id": file_record.file_id})
        try:
            _ = await self.bind(file_record.file_id, bound)
        except ServiceClientError as exc:
            # Office peer down/timeout — FileRecord уже durable; bind догонит при следующем open/repair.
            logger.warning(
                "docs_bind_after_create_failed",
                file_id=file_record.file_id,
                source_kind=_source_kind_metadata_value(spec.source_kind),
                error=str(exc),
            )

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
