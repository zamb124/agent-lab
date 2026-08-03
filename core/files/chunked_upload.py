"""Chunked file upload sessions (S3 multipart + Redis session state)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from pydantic import Field

from core.clients.redis_client import RedisClient, RedisOperationError
from core.config import get_settings
from core.context import require_active_company, require_context
from core.files.create_spec import FileCreateSpec, FileSourceKind
from core.files.file_repository import FileRepository
from core.files.models import FileRecord
from core.files.s3_client import S3Client, S3ClientFactory
from core.files.service import DocsBindHook, FilesService, RagIndexHook
from core.files.storage import original_name_with_extension, to_ascii_s3_metadata
from core.files.urls import normalize_files_route_segment
from core.logging import get_logger
from core.models import StrictBaseModel
from core.types import JsonObject

logger = get_logger(__name__)

_UPLOAD_SESSION_KEY_PREFIX = "files:upload:"


class ChunkedUploadPartRecord(StrictBaseModel):
    part_number: int = Field(ge=1)
    etag: str
    size: int = Field(ge=1)


class ChunkedUploadSession(StrictBaseModel):
    upload_id: str
    file_id: str
    company_id: str
    user_id: str
    s3_bucket: str
    s3_key: str
    s3_upload_id: str
    original_name: str
    content_type: str
    file_size: int = Field(ge=1)
    chunk_size_bytes: int = Field(ge=1)
    bytes_received: int = Field(default=0, ge=0)
    parts: list[ChunkedUploadPartRecord] = Field(default_factory=list)
    spec_json: str
    content_sha256_hex: str | None = None
    files_route_segment: str = Field(min_length=1)


class ChunkedUploadInitResult(StrictBaseModel):
    upload_id: str
    file_id: str
    chunk_size_bytes: int
    file_size: int


def _session_redis_key(upload_id: str) -> str:
    return f"{_UPLOAD_SESSION_KEY_PREFIX}{upload_id}"


def _redis() -> RedisClient:
    return RedisClient(get_settings().database.redis_url)


def _source_kind_wire(source_kind: FileSourceKind | str) -> str:
    return FileSourceKind(source_kind).value


class ChunkedUploadService:
    """Init / part / complete / abort для больших файлов через S3 multipart."""

    def __init__(
        self,
        file_repository: FileRepository,
        *,
        files_route_segment: str,
        rag_index_hook: RagIndexHook | None = None,
        docs_bind_hook: DocsBindHook | None = None,
    ) -> None:
        self._files_route_segment: str = normalize_files_route_segment(files_route_segment)
        self._files: FilesService = FilesService(
            file_repository=file_repository,
            files_route_segment=self._files_route_segment,
            rag_index_hook=rag_index_hook,
            docs_bind_hook=docs_bind_hook,
        )
        self._s3_client: S3Client | None = None

    async def _s3(self) -> S3Client:
        if self._s3_client is None:
            self._s3_client = S3ClientFactory.create_default_client()
        return self._s3_client

    async def init_upload(
        self,
        *,
        spec: FileCreateSpec,
        original_name: str,
        content_type: str,
        file_size: int,
        content_sha256_hex: str | None = None,
        route_segment: str | None = None,
    ) -> ChunkedUploadInitResult:
        settings = get_settings()
        if not settings.s3.enabled or not settings.s3.default_bucket:
            raise RuntimeError("S3 is not configured")
        files_cfg = settings.files
        if file_size <= 0:
            raise ValueError("file_size must be > 0")
        if file_size > files_cfg.max_upload_bytes:
            raise ValueError(
                f"file_size {file_size} exceeds max_upload_bytes {files_cfg.max_upload_bytes}"
            )
        if content_type.strip() == "":
            raise ValueError("content_type is required")

        context = require_context()
        company_id = require_active_company().company_id
        if company_id == "":
            raise ValueError("active company is required for chunked upload")
        user_id = context.user.user_id
        files_route_segment = (
            normalize_files_route_segment(route_segment)
            if route_segment is not None
            else self._files_route_segment
        )

        file_id = f"file_{uuid.uuid4().hex[:12]}"
        upload_id = f"upl_{uuid.uuid4().hex}"
        effective_name = original_name_with_extension(original_name, content_type)
        extension = Path(effective_name).suffix or ".bin"
        s3_key = f"files/{file_id}_{uuid.uuid4().hex[:16]}{extension}"

        metadata: JsonObject = dict(spec.metadata) if spec.metadata else {}
        metadata["source_kind"] = _source_kind_wire(spec.source_kind)
        s3_metadata = to_ascii_s3_metadata(metadata)

        s3_client = await self._s3()
        s3_upload_id = await s3_client.create_multipart_upload(
            s3_key,
            content_type=content_type,
            metadata=s3_metadata,
        )
        bucket_key = s3_client.require_bucket_config_key()

        session = ChunkedUploadSession(
            upload_id=upload_id,
            file_id=file_id,
            company_id=company_id,
            user_id=user_id,
            s3_bucket=bucket_key,
            s3_key=s3_key,
            s3_upload_id=s3_upload_id,
            original_name=effective_name,
            content_type=content_type,
            file_size=file_size,
            chunk_size_bytes=files_cfg.chunk_size_bytes,
            bytes_received=0,
            parts=[],
            spec_json=spec.model_dump_json(),
            content_sha256_hex=content_sha256_hex,
            files_route_segment=files_route_segment,
        )
        await self._save_session(session)
        return ChunkedUploadInitResult(
            upload_id=upload_id,
            file_id=file_id,
            chunk_size_bytes=files_cfg.chunk_size_bytes,
            file_size=file_size,
        )

    async def upload_part(
        self,
        upload_id: str,
        part_number: int,
        data: bytes,
    ) -> ChunkedUploadPartRecord:
        session = await self._load_session(upload_id)
        self._assert_session_owner(session)

        if part_number < 1:
            raise ValueError("part_number must be >= 1")
        expected_number = len(session.parts) + 1
        if part_number != expected_number:
            raise ValueError(
                f"part_number must be sequential: expected {expected_number}, got {part_number}"
            )
        if len(data) == 0:
            raise ValueError("empty part body")

        remaining = session.file_size - session.bytes_received
        if remaining <= 0:
            raise ValueError("all bytes already received")
        if len(data) > remaining:
            raise ValueError(
                f"part size {len(data)} exceeds remaining bytes {remaining}"
            )
        is_last = len(data) == remaining
        if not is_last and len(data) != session.chunk_size_bytes:
            raise ValueError(
                f"non-final part must be exactly {session.chunk_size_bytes} bytes, got {len(data)}"
            )

        s3_client = await self._s3()
        etag = await s3_client.upload_part(
            session.s3_key,
            upload_id=session.s3_upload_id,
            part_number=part_number,
            data=data,
        )
        part = ChunkedUploadPartRecord(
            part_number=part_number,
            etag=etag,
            size=len(data),
        )
        session.parts.append(part)
        session.bytes_received += len(data)
        await self._save_session(session)
        return part

    async def complete_upload(self, upload_id: str) -> FileRecord:
        session = await self._load_session(upload_id)
        self._assert_session_owner(session)
        if session.bytes_received != session.file_size:
            raise ValueError(
                f"incomplete upload: received {session.bytes_received} of {session.file_size}"
            )
        if len(session.parts) == 0:
            raise ValueError("complete requires at least one part")

        s3_client = await self._s3()
        await s3_client.complete_multipart_upload(
            session.s3_key,
            upload_id=session.s3_upload_id,
            parts=[(part.part_number, part.etag) for part in session.parts],
        )

        checksum = session.content_sha256_hex
        if checksum is None:
            checksum = await self._sha256_s3_object(session.s3_key)

        spec = FileCreateSpec.model_validate_json(session.spec_json)
        file_record = await self._files.register_s3(
            spec,
            s3_key=session.s3_key,
            s3_bucket=session.s3_bucket,
            original_name=session.original_name,
            content_type=session.content_type,
            file_size=session.file_size,
            existing_file_id=session.file_id,
            content_sha256_hex=checksum,
            route_segment=session.files_route_segment,
        )
        await self._delete_session(upload_id)
        return file_record

    async def abort_upload(self, upload_id: str) -> None:
        session = await self._load_session(upload_id)
        self._assert_session_owner(session)
        s3_client = await self._s3()
        await s3_client.abort_multipart_upload(
            session.s3_key,
            upload_id=session.s3_upload_id,
        )
        await self._delete_session(upload_id)

    async def _sha256_s3_object(self, s3_key: str) -> str:
        s3_client = await self._s3()
        body = await s3_client.open_object_body(s3_key)
        hasher = hashlib.sha256()
        try:
            while True:
                chunk = await body.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
        finally:
            body.close()
        return hasher.hexdigest()

    def _assert_session_owner(self, session: ChunkedUploadSession) -> None:
        company_id = require_active_company().company_id
        user_id = require_context().user.user_id
        if session.company_id != company_id:
            raise ValueError("upload session company mismatch")
        if session.user_id != user_id:
            raise ValueError("upload session user mismatch")

    async def _save_session(self, session: ChunkedUploadSession) -> None:
        ttl = get_settings().files.upload_session_ttl_seconds
        redis = _redis()
        key = _session_redis_key(session.upload_id)
        ok = await redis.set(key, session.model_dump_json(), ttl=ttl)
        if not ok:
            raise RedisOperationError(f"failed to persist upload session {session.upload_id}")

    async def _load_session(self, upload_id: str) -> ChunkedUploadSession:
        if upload_id.strip() == "":
            raise ValueError("upload_id is required")
        redis = _redis()
        raw = await redis.get(_session_redis_key(upload_id))
        if raw is None:
            raise ValueError(f"upload session not found: {upload_id}")
        return ChunkedUploadSession.model_validate_json(raw)

    async def _delete_session(self, upload_id: str) -> None:
        redis = _redis()
        _ = await redis.delete(_session_redis_key(upload_id))


__all__ = [
    "ChunkedUploadInitResult",
    "ChunkedUploadPartRecord",
    "ChunkedUploadService",
    "ChunkedUploadSession",
]
