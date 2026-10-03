"""
Единый файловый HTTP API платформы.

Mount на каждом сервисе с include_platform_routers:
`/{service}/api/v1/files/*` (office: `/documents/api/v1/files/*`).
Клиентский upload — только chunked `/uploads*`. Download URL —
`/{same-segment}/api/v1/files/download/{file_id}` (без frontend-канона).
"""

from __future__ import annotations

from pathlib import Path
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
from core.context import get_context, require_active_company
from core.di.platform import Di
from core.errors.boundary import PlatformAccessDeniedError, PlatformNotFoundError
from core.files.chunked_upload import (
    ChunkedUploadInitResult,
    ChunkedUploadPartRecord,
)
from core.files.create_spec import FileCreateSpec
from core.files.file_ref import FileRef, stored_file_ref
from core.files.http_range import RangeNotSatisfiableError
from core.files.models import FileReadPreviewResponse, FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import (
    AnonymousPrincipal,
    FilePrincipal,
    SessionPrincipal,
)
from core.files.read_preview import build_stored_file_text_preview
from core.files.reader.exceptions import FileReadError
from core.files.streaming import stream_file_handle
from core.files.urls import (
    files_api_prefix,
    normalize_files_route_segment,
    require_files_route_segment,
)
from core.http import get_httpx_client, http_header_text
from core.logging import get_logger
from core.models import StrictBaseModel

logger = get_logger(__name__)


async def _require_company_can_view(authz: AuthzService) -> str:
    company_id = require_active_company().company_id
    await authz.require_can_view(AuthzObject.company(company_id))
    return company_id


def _file_principal_for_request(request: Request) -> FilePrincipal:
    company_id = get_request_company_id(request)
    context = get_context()
    if context is not None and company_id is not None:
        return SessionPrincipal(user_id=context.user.user_id, company_id=company_id)
    return AnonymousPrincipal()


async def _open_file_for_request(
    file_id: str,
    request: Request,
    authz: AuthzService,
) -> FileRecord:
    try:
        handle = await FileGate(authz).open(file_id, _file_principal_for_request(request))
    except PlatformNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PlatformAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="File access denied.") from exc
    return handle.record


class RegisterS3Request(StrictBaseModel):
    spec: FileCreateSpec
    s3_key: str
    storage_id: str
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


def build_files_router(*, files_route_segment: str) -> APIRouter:
    router = APIRouter(tags=["files"])
    route_segment = normalize_files_route_segment(files_route_segment)

    async def upload_config() -> FilesUploadConfigResponse:
        files_cfg = get_settings().files
        return FilesUploadConfigResponse(
            max_upload_bytes=files_cfg.max_upload_bytes,
            chunk_size_bytes=files_cfg.chunk_size_bytes,
            upload_session_ttl_seconds=files_cfg.upload_session_ttl_seconds,
        )

    async def init_chunked_upload(body: ChunkedUploadInitRequest, di: Di) -> ChunkedUploadInitResult:
        _ = await _require_company_can_view(di.authz_service)
        upload_settings = get_settings()
        if not upload_settings.s3.enabled or not upload_settings.s3.bucket_name:
            raise HTTPException(status_code=503, detail="S3 is not configured.")
        service = di.chunked_upload_service
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
        di: Di,
    ) -> ChunkedUploadPartRecord:
        _ = await _require_company_can_view(di.authz_service)
        upload_settings = get_settings()
        max_part = upload_settings.files.chunk_size_bytes
        data = await _read_body_with_limit(request, max_part)
        service = di.chunked_upload_service
        try:
            return await service.upload_part(upload_id, part_number, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def complete_chunked_upload(upload_id: str, di: Di) -> FileRef:
        _ = await _require_company_can_view(di.authz_service)
        service = di.chunked_upload_service
        try:
            file_record = await service.complete_upload(upload_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return stored_file_ref(file_record, route_segment=route_segment)

    async def abort_chunked_upload(upload_id: str, di: Di) -> Response:
        _ = await _require_company_can_view(di.authz_service)
        service = di.chunked_upload_service
        try:
            await service.abort_upload(upload_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    async def register_s3(body: RegisterS3Request, di: Di) -> FileRef:
        _ = await _require_company_can_view(di.authz_service)
        register_settings = get_settings()
        if not register_settings.s3.enabled:
            raise HTTPException(status_code=503, detail="S3 is not configured.")
        service = di.files_service
        try:
            file_record = await service.register_s3(
                body.spec,
                s3_key=body.s3_key,
                storage_id=body.storage_id,
                original_name=body.original_name,
                content_type=body.content_type,
                file_size=body.file_size,
                route_segment=route_segment,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return stored_file_ref(file_record, route_segment=route_segment)

    async def download_file(file_id: str, request: Request, di: Di) -> StreamingResponse | Response:
        try:
            handle = await FileGate(di.authz_service).open(
                file_id,
                _file_principal_for_request(request),
            )
        except PlatformNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PlatformAccessDeniedError as exc:
            raise HTTPException(status_code=403, detail="File access denied.") from exc

        file_record = handle.record
        s3_key = file_record.s3_key
        content_type = file_record.content_type
        if file_record.storage_id != "" and s3_key != "":
            if content_type == "":
                raise HTTPException(status_code=500, detail="File content_type is missing.")
            range_raw = request.headers.get("range")
            range_header = range_raw.strip() if isinstance(range_raw, str) else None
            try:
                return await stream_file_handle(
                    handle=handle,
                    content_type=content_type,
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

        response_content_type_raw = http_header_text(
            upstream_response.headers,
            "content-type",
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

    async def get_file_text_preview(
        file_id: str,
        request: Request,
        di: Di,
    ) -> FileReadPreviewResponse:
        _ = await _open_file_for_request(file_id, request, di.authz_service)
        try:
            file_record = await di.files_service.get(file_id)
            return await build_stored_file_text_preview(
                file_id=file_id,
                original_name=file_record.original_name,
            )
        except FileReadError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def get_file_metadata(file_id: str, request: Request, di: Di) -> FileRef:
        file_record = await _open_file_for_request(file_id, request, di.authz_service)
        return stored_file_ref(file_record)

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
        response_model=FileRef,
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
        response_model=FileRef,
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
        response_model=FileRef,
    )
    return router


__all__ = ["build_files_router", "files_api_prefix", "require_files_route_segment"]
