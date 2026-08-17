"""
Единый файловый HTTP API платформы.

Mount на каждом сервисе с include_platform_routers:
`/{service}/api/v1/files/*` (office: `/documents/api/v1/files/*`).
Клиентский upload — только chunked `/uploads*`. Download URL —
`/{same-segment}/api/v1/files/download/{file_id}` (без frontend-канона).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, cast
from urllib.parse import urlparse

import httpx
from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import Field

from core.app_state import get_request_company_id
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.config import get_settings
from core.context import require_active_company
from core.documents.placement import DocsPlacement
from core.files.chunked_upload import (
    ChunkedUploadInitResult,
    ChunkedUploadPartRecord,
    ChunkedUploadService,
)
from core.files.create_spec import FileCreateSpec
from core.files.http_range import RangeNotSatisfiableError
from core.files.models import FileReadPreviewResponse, FileRecord, FileResponse
from core.files.read_preview import build_stored_file_text_preview
from core.files.reader.exceptions import FileReadError
from core.files.s3_client import S3ClientFactory
from core.files.service import FilesService
from core.files.streaming import stream_s3_file
from core.files.urls import (
    files_api_prefix,
    normalize_files_route_segment,
    require_files_route_segment,
)
from core.http import get_httpx_client
from core.logging import get_logger
from core.models import StrictBaseModel

logger = get_logger(__name__)


class _AuthzContainerView(Protocol):
    @property
    def authz_service(self) -> AuthzService: ...


class _AppStateView(Protocol):
    container: object


class _AppView(Protocol):
    state: _AppStateView


def _authz_container(request: Request) -> _AuthzContainerView:
    app = cast(_AppView, request.app)
    return cast(_AuthzContainerView, app.state.container)


async def _require_company_can_view(request: Request) -> str:
    company_id = require_active_company().company_id
    await _authz_container(request).authz_service.require_can_view(AuthzObject.company(company_id))
    return company_id


async def _ensure_file_record_access(request: Request, file_record: FileRecord) -> None:
    if file_record.is_public:
        return
    active_company_id = get_request_company_id(request)
    if active_company_id is None:
        raise HTTPException(status_code=403, detail="File access denied.")
    if file_record.company_id is None:
        raise HTTPException(status_code=403, detail="File access denied.")
    if active_company_id != file_record.company_id:
        raise HTTPException(status_code=403, detail="File access denied.")
    await _authz_container(request).authz_service.require_can_view(
        AuthzObject.company(file_record.company_id)
    )


class RegisterS3Request(StrictBaseModel):
    spec: FileCreateSpec
    s3_key: str
    s3_bucket: str
    original_name: str
    content_type: str
    file_size: int


class ChunkedUploadInitRequest(StrictBaseModel):
    spec: FileCreateSpec
    original_name: str
    content_type: str
    file_size: int = Field(ge=1)
    content_sha256_hex: str | None = None


class FilesUploadConfigResponse(StrictBaseModel):
    max_upload_bytes: int = Field(ge=1)
    chunk_size_bytes: int = Field(ge=1)
    upload_session_ttl_seconds: int = Field(ge=1)


async def _read_body_with_limit(request: Request, max_bytes: int) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    parts: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Part exceeds {max_bytes} bytes.",
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


def build_files_router(
    get_files_service: Callable[[], FilesService],
    get_chunked_upload_service: Callable[[], ChunkedUploadService] | None = None,
    *,
    files_route_segment: str | None = None,
) -> APIRouter:
    router = APIRouter(tags=["files"])
    route_segment = (
        normalize_files_route_segment(files_route_segment)
        if files_route_segment is not None
        else require_files_route_segment()
    )

    def _chunked() -> ChunkedUploadService:
        if get_chunked_upload_service is None:
            raise HTTPException(status_code=503, detail="Chunked upload is not configured.")
        return get_chunked_upload_service()

    async def upload_config() -> FilesUploadConfigResponse:
        files_cfg = get_settings().files
        return FilesUploadConfigResponse(
            max_upload_bytes=files_cfg.max_upload_bytes,
            chunk_size_bytes=files_cfg.chunk_size_bytes,
            upload_session_ttl_seconds=files_cfg.upload_session_ttl_seconds,
        )

    async def init_chunked_upload(
        body: ChunkedUploadInitRequest, request: Request
    ) -> ChunkedUploadInitResult:
        _ = await _require_company_can_view(request)
        upload_settings = get_settings()
        if not upload_settings.s3.enabled or not upload_settings.s3.default_bucket:
            raise HTTPException(status_code=503, detail="S3 is not configured.")
        service = _chunked()
        try:
            return await service.init_upload(
                spec=body.spec,
                original_name=_safe_original_name(body.original_name),
                content_type=body.content_type,
                file_size=body.file_size,
                content_sha256_hex=body.content_sha256_hex,
                route_segment=route_segment,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def put_chunked_upload_part(
        upload_id: str,
        part_number: int,
        request: Request,
    ) -> ChunkedUploadPartRecord:
        _ = await _require_company_can_view(request)
        upload_settings = get_settings()
        max_part = upload_settings.files.chunk_size_bytes
        data = await _read_body_with_limit(request, max_part)
        service = _chunked()
        try:
            return await service.upload_part(upload_id, part_number, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def complete_chunked_upload(upload_id: str, request: Request) -> FileResponse:
        _ = await _require_company_can_view(request)
        service = _chunked()
        try:
            file_record = await service.complete_upload(upload_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return FileResponse.from_record(file_record, route_segment=route_segment)

    async def abort_chunked_upload(upload_id: str, request: Request) -> Response:
        _ = await _require_company_can_view(request)
        service = _chunked()
        try:
            await service.abort_upload(upload_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    async def register_s3(body: RegisterS3Request, request: Request) -> FileResponse:
        _ = await _require_company_can_view(request)
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
                route_segment=route_segment,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return FileResponse.from_record(file_record, route_segment=route_segment)

    async def bind_file(file_id: str, placement: DocsPlacement, request: Request) -> dict[str, str]:
        _ = await _require_company_can_view(request)
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

        await _ensure_file_record_access(request, file_record)

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
                    raise HTTPException(
                        status_code=404, detail="File not found in storage."
                    ) from exc
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
                raise HTTPException(
                    status_code=404, detail="File not found at storage URL."
                ) from exc
            raise HTTPException(status_code=502, detail="Upstream download failed.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Upstream download failed.") from exc

        response_content_type_raw = cast(
            str | None,
            upstream_response.headers.get("content-type"),
        )
        if (
            not isinstance(response_content_type_raw, str)
            or response_content_type_raw.strip() == ""
        ):
            raise HTTPException(status_code=502, detail="Upstream response missing content-type.")
        media_type = response_content_type_raw.split(";")[0].strip()
        return StreamingResponse(
            content=iter([upstream_response.content]),
            media_type=media_type,
        )

    async def get_file_text_preview(file_id: str, request: Request) -> FileReadPreviewResponse:
        service = get_files_service()
        try:
            file_record = await service.get(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        await _ensure_file_record_access(request, file_record)
        try:
            return await build_stored_file_text_preview(
                file_id=file_id,
                original_name=file_record.original_name,
            )
        except FileReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_file_metadata(file_id: str, request: Request) -> FileResponse:
        service = get_files_service()
        try:
            file_record = await service.get(file_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        await _ensure_file_record_access(request, file_record)
        return FileResponse.from_record(file_record)

    router.add_api_route(
        "/upload-config",
        upload_config,
        methods=["GET"],
        response_model=FilesUploadConfigResponse,
    )
    router.add_api_route(
        "/uploads",
        init_chunked_upload,
        methods=["POST"],
        response_model=ChunkedUploadInitResult,
    )
    router.add_api_route(
        "/uploads/{upload_id}/parts/{part_number}",
        put_chunked_upload_part,
        methods=["PUT"],
        response_model=ChunkedUploadPartRecord,
    )
    router.add_api_route(
        "/uploads/{upload_id}/complete",
        complete_chunked_upload,
        methods=["POST"],
        response_model=FileResponse,
    )
    router.add_api_route(
        "/uploads/{upload_id}",
        abort_chunked_upload,
        methods=["DELETE"],
        status_code=204,
        response_model=None,
    )
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


__all__ = ["build_files_router", "files_api_prefix", "require_files_route_segment"]
