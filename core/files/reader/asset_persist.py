"""Persist page assets as FileRecord on RAG index-path."""

from __future__ import annotations

from core.files.checksum import compute_content_checksum_sha256
from core.files.create_spec import FileSourceKind, FileSourceRef
from core.files.file_ref import FileRef
from core.files.registry import build_file_create_spec
from core.files.service import FilesService


async def persist_extract_asset(
    *,
    files_service: FilesService,
    namespace_id: str,
    source_file_id: str,
    original_name: str,
    content_type: str,
    data: bytes,
) -> FileRef:
    spec = build_file_create_spec(
        source_kind=FileSourceKind.RAG_DOCUMENT,
        source_ref=FileSourceRef(namespace_id=namespace_id, entity_id=source_file_id),
        metadata={"source_file_id": source_file_id},
    )
    record = await files_service.create(
        spec,
        data,
        original_name=original_name,
        content_type=content_type,
        content_sha256_hex=compute_content_checksum_sha256(data),
    )
    return FileRef.model_validate(record)
