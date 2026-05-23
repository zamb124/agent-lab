"""Сохранение уже собранных байтов через FileProcessor (S3 + FileRepository)."""

from __future__ import annotations

from core.files.models import FileMetadata
from core.files.processors import FileProcessor


async def write_bytes_via_processor(
    *,
    data: bytes,
    content_type: str,
    original_name: str,
    file_processor: FileProcessor,
    uploaded_by: str | None,
    company_id: str,
    download_url_prefix: str,
    content_sha256_hex: str,
    public: bool = True,
) -> FileMetadata:
    return await file_processor.persist_uploaded_file(
        data=data,
        original_name=original_name,
        content_type=content_type,
        uploaded_by=uploaded_by,
        company_id=company_id,
        public=public,
        download_url_prefix=download_url_prefix,
        content_sha256_hex=content_sha256_hex,
    )
