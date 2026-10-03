"""Anonymous viewer routes (stream/frame/save) для non-OnlyOffice handlers."""

from __future__ import annotations

from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, Response

from apps.office.config import get_office_settings
from apps.office.di import Di
from apps.office.models.link import DocumentLink
from apps.office.services.viewer_frame import render_viewer_frame_html
from apps.office.services.viewer_handlers._urls import viewer_save_url, viewer_stream_url
from apps.office.services.viewer_handlers.text_handler import TEXT_MAX_EDIT_BYTES
from core.clients.onlyoffice import OnlyOfficeJwtError
from core.documents.viewer.jwt import decode_viewer_save_token, decode_viewer_stream_token
from core.documents.viewer.models import OfficeViewerSaveTokenClaims, OfficeViewerStreamTokenClaims
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SignedFileGrant
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.websocket import WsCommandError

logger = get_logger(__name__)
router = APIRouter(tags=["office-viewer"])


@router.get("/viewer-stream")
async def viewer_stream(
    di: Di,
    token: Annotated[str, Query(description="JWT office_view")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise WsCommandError("unavailable", "office is not configured", error_code="unavailable")
    try:
        claims = decode_viewer_stream_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise WsCommandError("unauthorized", "Invalid viewer token", error_code="unauthorized") from exc
    await _authorize_viewer_claims(claims)
    meta = await di.files_service.get_optional(claims.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    if meta.company_id != claims.company_id:
        raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    handle = await FileGate().open_record(
        meta,
        SignedFileGrant(file_id=claims.file_id, company_id=claims.company_id),
    )
    try:
        body = await handle.read_bytes()
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        logger.warning(
            "office.viewer.stream.s3.error.file_id",
            file_id=claims.file_id,
            storage_id=meta.storage_id,
            key=meta.s3_key,
            code=code,
        )
        raise WsCommandError("upstream", f"S3 did not return the object: {code}", error_code="upstream") from exc
    content_type = claims.content_type or meta.content_type or "application/octet-stream"
    disposition = "inline"
    if claims.handler == "binary":
        disposition = "attachment"
    return Response(
        content=body,
        media_type=content_type,
        headers={"Content-Disposition": f'{disposition}; filename="{meta.original_name}"'},
    )


@router.get("/viewer-frame")
async def viewer_frame(
    di: Di,
    request: Request,
    token: Annotated[str, Query(description="JWT office_view")],
) -> HTMLResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise WsCommandError("unavailable", "office is not configured", error_code="unavailable")
    try:
        claims = decode_viewer_stream_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise WsCommandError("unauthorized", "Invalid viewer token", error_code="unauthorized") from exc
    await _authorize_viewer_claims(claims)
    meta = await di.files_service.get_optional(claims.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    base = build_service_base_url(request)
    stream_url = viewer_stream_url(
        base_url=base,
        handler=claims.handler,
        viewer_scope=claims.viewer_scope,
        file_id=claims.file_id,
        company_id=claims.company_id,
        content_type=claims.content_type,
        secret=integ.jwt_secret,
        ttl_seconds=integ.download_token_ttl_seconds,
        edit_mode=claims.edit_mode,
        public_link_token_hash=claims.public_link_token_hash,
    )
    save_url = ""
    if claims.handler == "text" and claims.edit_mode:
        save_url = viewer_save_url(
            base_url=base,
            viewer_scope=claims.viewer_scope,
            file_id=claims.file_id,
            company_id=claims.company_id,
            secret=integ.jwt_secret,
            ttl_seconds=integ.download_token_ttl_seconds,
            public_link_token_hash=claims.public_link_token_hash,
        )
    html = render_viewer_frame_html(
        claims=claims,
        stream_url=stream_url,
        save_url=save_url,
        title=meta.original_name,
    )
    return HTMLResponse(content=html)


@router.post("/viewer-save")
async def viewer_save(
    di: Di,
    request: Request,
    token: Annotated[str, Query(description="JWT office_view_save")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise WsCommandError("unavailable", "office is not configured", error_code="unavailable")
    try:
        claims = decode_viewer_save_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise WsCommandError("unauthorized", "Invalid viewer save token", error_code="unauthorized") from exc
    await _authorize_viewer_claims(claims)
    body = await request.body()
    if len(body) == 0:
        raise WsCommandError("ws_invalid_payload", "Empty save body", error_code="ws_invalid_payload")
    if len(body) > TEXT_MAX_EDIT_BYTES:
        raise WsCommandError(
            "payload_too_large",
            f"Text size exceeds the limit {TEXT_MAX_EDIT_BYTES} bytes",
            error_code="ws_invalid_payload",
        )
    meta = await di.files_service.get_optional(claims.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    if meta.company_id != claims.company_id:
        raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    content_type = meta.content_type or "text/plain"
    normalized_content_type = content_type.split(";", 1)[0].strip()
    _ = await di.files_service.replace_content(
        meta,
        body,
        content_type=normalized_content_type,
        expected_checksum=meta.checksum,
    )
    return Response(status_code=204)


async def _authorize_viewer_claims(
    claims: OfficeViewerStreamTokenClaims | OfficeViewerSaveTokenClaims,
) -> None:
    if claims.public_link_token_hash is not None:
        link = await DocumentLink.by_enabled_token(claims.public_link_token_hash)
        if link is None or link.target_kind != "file" or link.target_id != claims.file_id:
            raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
        if link.company_id != claims.company_id:
            raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
        if link.permission == "viewer" and isinstance(claims, OfficeViewerSaveTokenClaims):
            raise WsCommandError("forbidden", "Save is forbidden", error_code="forbidden")
        return

    if claims.viewer_scope == "catalog":
        binding_row = await FileRecord.for_company(claims.file_id, claims.company_id)
        if binding_row is None or binding_row.catalog_id is None:
            raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
        return
    if claims.viewer_scope == "file":
        return
    raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
