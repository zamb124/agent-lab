"""
Единый файловый HTTP API платформы.

Mount только на frontend: /frontend/api/v1/files/*
"""

from __future__ import annotations

import mimetypes
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, cast
from urllib.parse import urlparse

import httpx
from botocore.exceptions import ClientError
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from core.config import get_settings
from core.context import require_active_company
from core.documents.placement import DocsPlacement
from core.files.audio_transcode import AudioTranscodeError
from core.files.checksum import compute_content_checksum_sha256
from core.files.create_spec import FileCreateSpec
from core.files.http_range import RangeNotSatisfiableError
from core.files.models import FileReadPreviewResponse, FileRecord, FileResponse
from core.files.read_preview import build_stored_file_text_preview
from core.files.reader.exceptions import FileReadError
from core.files.s3_client import S3ClientFactory
from core.files.service import FilesService
from core.files.storage import CANONICAL_DOWNLOAD_URL_PREFIX
from core.files.streaming import stream_s3_file
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)
_UPLOAD_READ_CHUNK_BYTES = 1024 * 1024


class RegisterS3Request(StrictBaseModel):
    spec: FileCreateSpec
    s3_key: str
    s3_bucket: str
    original_name: str
    content_type: str
    file_size: int


async def _read_upload_with_limit(file: UploadFile, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    parts: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {max_bytes} bytes.",
            )
        parts.append(chunk)
    return b"".join(parts)


def _safe_original_name(raw: str | None) -> str:
    if raw is None or raw == "":
        return "file"
    name = Path(raw).name.strip()
    return name[:255] if name and name != "." else "file"


def _is_http_url(url: str) -> bool:
    if url == "":
        return False
    parsed = urlparse(url)
    return parsed.scheme in ("http", "https")


def _ensure_file_record_access(file_record: FileRecord) -> None:
    if file_record.is_public:
        return
    active_company = require_active_company()
    if file_record.company_id is None:
        raise HTTPException(status_code=403, detail="File access denied.")
    if active_company.company_id != file_record.company_id:
        raise HTTPException(status_code=403, detail="File access denied.")


def build_files_router(get_files_service: Callable[[], FilesService]) -> APIRouter:
    router = APIRouter(tags=["files"])
    settings = get_settings()
    max_upload_bytes = settings.files.max_upload_bytes

    async def upload_file(
        file: Annotated[UploadFile, File()],
        spec: Annotated[str, Form()],
    ) -> FileResponse:
        upload_settings = get_settings()
        if not upload_settings.s3.enabled or not upload_settings.s3.default_bucket:
            raise HTTPException(status_code=503, detail="S3 is not configured.")

        try:
            create_spec = FileCreateSpec.model_validate_json(spec)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid spec: {exc}") from exc

        data = await _read_upload_with_limit(file, max_upload_bytes)
        if len(data) == 0:
            raise HTTPException(status_code=400, detail="Пустой файл.")

        original_name = _safe_original_name(file.filename)
        guessed, _ = mimetypes.guess_type(original_name)
        raw_ct = file.content_type
        if isinstance(raw_ct, str) and raw_ct.strip():
            content_type = raw_ct.split(";")[0].strip()
        elif guessed:
            content_type = guessed
        else:
            content_type = "application/octet-stream"

        checksum = compute_content_checksum_sha256(data)
        service = get_files_service()
        try:
            file_record = await service.create(
                create_spec,
                data,
                original_name=original_name,
                content_type=content_type,
                content_sha256_hex=checksum,
            )
        except AudioTranscodeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        return FileResponse.from_record(file_record)

    async def register_s3(body: RegisterS3Request) -> FileResponse:
        register_settings = get_settings()
        if not register_settings.s3.enabled:
            raise HTTPException(status_code=503, detail="S3 is not configured.")
        service = get_files_service()
        try:
            file_record = await service.register_s3(
                body.spec,
                s3_key=body.s3_key,
                s3_bucket=body.s3_bucket,
                original_name=body.original_name,
                content_type=body.content_type,
                file_size=body.file_size,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse.from_record(file_record)

    async def bind_file(file_id: str, placement: DocsPlacement) -> dict[str, str]:
        service = get_files_service()
        try:
            result = await service.bind(file_id, placement)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    async def download_file(file_id: str, request: Request) -> StreamingResponse | Response:
        service = get_files_service()
        try:
            file_record = await service.get(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _ensure_file_record_access(file_record)

        s3_bucket = file_record.s3_bucket
        s3_key = file_record.s3_key
        content_type = file_record.content_type
        if s3_bucket != "" and s3_key != "":
            if content_type == "":
                raise HTTPException(status_code=500, detail="File content_type is missing.")
            s3_client = S3ClientFactory.create_client_for_bucket(s3_bucket)
            range_raw = request.headers.get("range")
            range_header = range_raw.strip() if isinstance(range_raw, str) else None
            try:
                return await stream_s3_file(
                    s3_client=s3_client,
                    s3_key=s3_key,
                    content_type=content_type,
                    bucket=None,
                    range_header=range_header,
                )
            except RangeNotSatisfiableError as exc:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{exc.total_size}"},
                )
            except ClientError as exc:
                code = exc.response["Error"]["Code"]
                status = exc.response["ResponseMetadata"]["HTTPStatusCode"]
                not_found = code in ("404", "NoSuchKey", "NotFound") or status == 404
                if not_found:
                    raise HTTPException(status_code=404, detail="File not found in storage.") from exc
                logger.exception("files.download_s3_failed", file_id=file_id)
                raise HTTPException(status_code=502, detail="Storage download failed.") from exc

        storage_url = file_record.storage_url
        if storage_url is None or storage_url == "":
            raise HTTPException(status_code=404, detail="File source is not configured.")
        if not _is_http_url(storage_url):
            raise HTTPException(status_code=404, detail="File source URL is not supported.")

        try:
            async with get_httpx_client(timeout=120.0) as client:
                upstream_response = await client.get(storage_url)
            _ = upstream_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            st = exc.response.status_code
            if st == 404:
                raise HTTPException(status_code=404, detail="File not found at storage URL.") from exc
            raise HTTPException(status_code=502, detail="Upstream download failed.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Upstream download failed.") from exc

        response_content_type_raw = cast(
            str | None,
            upstream_response.headers.get("content-type"),
        )
        if not isinstance(response_content_type_raw, str) or response_content_type_raw.strip() == "":
            raise HTTPException(status_code=502, detail="Upstream response missing content-type.")
        media_type = response_content_type_raw.split(";")[0].strip()
        return StreamingResponse(
            content=iter([upstream_response.content]),
            media_type=media_type,
        )

    async def get_file_text_preview(file_id: str) -> FileReadPreviewResponse:
        service = get_files_service()
        try:
            file_record = await service.get(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _ensure_file_record_access(file_record)
        try:
            return await build_stored_file_text_preview(
                file_id=file_id,
                original_name=file_record.original_name,
            )
        except FileReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_file_metadata(file_id: str) -> FileResponse:
        service = get_files_service()
        try:
            file_record = await service.get(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _ensure_file_record_access(file_record)
        return FileResponse.from_record(file_record)

    router.add_api_route("/", upload_file, methods=["POST"], response_model=FileResponse)
    router.add_api_route(
        "/register-s3",
        register_s3,
        methods=["POST"],
        response_model=FileResponse,
    )
    router.add_api_route(
        "/{file_id}/bind",
        bind_file,
        methods=["POST"],
    )
    router.add_api_route(
        "/download/{file_id}",
        download_file,
        methods=["GET"],
        response_class=StreamingResponse,
        response_model=None,
    )
    router.add_api_route(
        "/{file_id}/preview",
        get_file_text_preview,
        methods=["GET"],
        response_model=FileReadPreviewResponse,
    )
    router.add_api_route(
        "/{file_id}",
        get_file_metadata,
        methods=["GET"],
        response_model=FileResponse,
    )
    return router


__all__ = ["build_files_router", "CANONICAL_DOWNLOAD_URL_PREFIX"]
