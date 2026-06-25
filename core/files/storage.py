"""Private S3 + FileRepository persistence."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

from core.files.audio_transcode import (
    resolve_ios_transcode_source,
    transcode_audio_bytes_to_m4a_aac,
)
from core.files.file_repository import FileRepository
from core.files.models import FileRecord, FileStatus
from core.files.retention import FileRetentionKind, FileRetentionSpec, resolve_retention_ttl_seconds
from core.files.s3_client import S3Client, S3ClientFactory
from core.logging import get_logger
from core.types import JsonObject

logger = get_logger(__name__)

CANONICAL_DOWNLOAD_URL_PREFIX = "/frontend/api/v1/files/download"


def _to_ascii_s3_metadata(metadata: JsonObject) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw_key, raw_value in metadata.items():
        key = raw_key.strip()
        if isinstance(raw_value, Mapping) or (
            isinstance(raw_value, Sequence) and not isinstance(raw_value, str)
        ):
            value = json.dumps(raw_value, ensure_ascii=False, separators=(",", ":"))
        else:
            value = str(raw_value)
        out[key] = value if value.isascii() else quote(value, safe="")
    return out


def _original_name_with_extension(original_name: str, content_type: str) -> str:
    if Path(original_name).suffix:
        return original_name
    ext = mimetypes.guess_extension(content_type.strip(), strict=False)
    if ext and not original_name.endswith(ext):
        return f"{original_name}{ext}"
    return original_name


class FileStorage:
    def __init__(self, file_repository: FileRepository, bucket_name: str | None = None) -> None:
        self._file_repository: FileRepository = file_repository
        self._bucket_name: str | None = bucket_name
        self._s3_client: S3Client | None = None

    async def _get_s3_client(self) -> S3Client:
        if self._s3_client is None:
            if self._bucket_name:
                self._s3_client = S3ClientFactory.create_client_for_bucket(self._bucket_name)
            else:
                self._s3_client = S3ClientFactory.create_default_client()
        return self._s3_client

    async def close(self) -> None:
        if self._s3_client:
            await self._s3_client.close()
            self._s3_client = None

    async def upload_bytes(
        self,
        *,
        data: bytes,
        original_name: str,
        content_type: str,
        uploaded_by: str | None,
        company_id: str,
        is_public: bool,
        retention_kind: FileRetentionKind,
        ttl_seconds: int,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
        content_sha256_hex: str | None = None,
        existing_file_id: str | None = None,
    ) -> FileRecord:
        if len(data) == 0:
            raise ValueError("Пустой файл.")

        file_id = existing_file_id if existing_file_id else f"file_{uuid.uuid4().hex[:12]}"
        effective_name = _original_name_with_extension(original_name, content_type)

        needs_ios, src_suffix = resolve_ios_transcode_source(content_type, effective_name, data)
        if needs_ios:
            data = await transcode_audio_bytes_to_m4a_aac(data, src_suffix)
            content_type = "audio/mp4"
            stem = Path(effective_name).stem
            if stem == "" or stem == ".":
                stem = "voice"
            effective_name = f"{stem}.m4a"

        file_hash = hashlib.sha256(data).hexdigest()[:16]
        extension = Path(effective_name).suffix or ".bin"
        s3_key = f"files/{file_id}_{file_hash}{extension}"

        s3_client = await self._get_s3_client()
        s3_metadata = _to_ascii_s3_metadata(metadata or {})
        _ = await s3_client.upload_bytes(
            data=data,
            key=s3_key,
            metadata=s3_metadata,
            content_type=content_type,
            public=is_public,
        )

        created_at = datetime.now(UTC)
        expires_at: datetime | None
        if ttl_seconds == 0:
            expires_at = None
        else:
            expires_at = created_at + timedelta(seconds=ttl_seconds)

        checksum = content_sha256_hex if content_sha256_hex else hashlib.sha256(data).hexdigest()
        file_record = FileRecord(
            file_id=file_id,
            provider=s3_client.provider_name,
            original_name=effective_name,
            content_type=content_type,
            file_size=len(data),
            s3_bucket=s3_client.require_bucket_config_key(),
            s3_key=s3_key,
            s3_endpoint=s3_client.endpoint_url,
            uploaded_by=uploaded_by,
            company_id=company_id,
            is_public=is_public,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            checksum=checksum,
            retention_kind=retention_kind,
            expires_at=expires_at,
            download_url=f"{CANONICAL_DOWNLOAD_URL_PREFIX}/{file_id}",
        )
        _ = await self._file_repository.set(file_record)
        logger.info(
            "file stored: file_id=%s original_name=%s bytes=%s",
            file_id,
            effective_name,
            len(data),
        )
        return file_record

    async def register_s3_object(
        self,
        *,
        s3_key: str,
        s3_bucket: str,
        original_name: str,
        content_type: str,
        file_size: int,
        uploaded_by: str | None,
        company_id: str,
        is_public: bool,
        retention_kind: FileRetentionKind,
        ttl_seconds: int,
        metadata: JsonObject | None = None,
        tags: list[str] | None = None,
    ) -> FileRecord:
        file_id = f"file_{uuid.uuid4().hex[:12]}"
        s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
        try:
            provider_name = s3_client.provider_name
            endpoint_url = s3_client.endpoint_url
        finally:
            await s3_client.close()

        created_at = datetime.now(UTC)
        expires_at: datetime | None
        if ttl_seconds == 0:
            expires_at = None
        else:
            expires_at = created_at + timedelta(seconds=ttl_seconds)

        file_record = FileRecord(
            file_id=file_id,
            provider=provider_name,
            original_name=original_name,
            content_type=content_type,
            file_size=file_size,
            s3_bucket=s3_bucket,
            s3_key=s3_key,
            s3_endpoint=endpoint_url,
            uploaded_by=uploaded_by,
            company_id=company_id,
            is_public=is_public,
            status=FileStatus.READY,
            metadata=metadata or {},
            tags=tags or [],
            retention_kind=retention_kind,
            expires_at=expires_at,
            download_url=f"{CANONICAL_DOWNLOAD_URL_PREFIX}/{file_id}",
        )
        _ = await self._file_repository.set(file_record)
        return file_record

    async def get(self, file_id: str) -> FileRecord | None:
        return await self._file_repository.get(file_id)

    async def save(self, file_record: FileRecord) -> FileRecord:
        _ = await self._file_repository.set(file_record)
        return file_record

    async def delete(self, file_id: str) -> bool:
        file_record = await self.get(file_id)
        if file_record is None:
            return False
        s3_client = S3ClientFactory.create_client_for_bucket(file_record.s3_bucket)
        try:
            _ = await s3_client.delete_file(file_record.s3_key)
        finally:
            await s3_client.close()
        _ = await self._file_repository.delete(file_id)
        return True


def retention_fields_from_spec(retention_spec: object) -> tuple[FileRetentionKind, int]:
    if not isinstance(retention_spec, FileRetentionSpec):
        raise TypeError("retention must be FileRetentionSpec")
    kind = retention_spec.kind
    ttl_seconds = resolve_retention_ttl_seconds(retention_spec)
    return kind, ttl_seconds
