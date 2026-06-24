"""Anonymous viewer routes (stream/frame/save) для non-OnlyOffice handlers."""

from __future__ import annotations

import hashlib
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from apps.office.config import get_office_settings
from apps.office.container import OfficeContainer
from apps.office.dependencies import ContainerDep
from apps.office.services.viewer_frame import render_viewer_frame_html
from apps.office.services.viewer_handlers._urls import viewer_save_url, viewer_stream_url
from apps.office.services.viewer_handlers.text_handler import TEXT_MAX_EDIT_BYTES
from apps.office.services.viewer_service import browser_public_base_url, file_viewer_binding_id
from core.clients.onlyoffice import OnlyOfficeJwtError
from core.documents.viewer.jwt import decode_viewer_save_token, decode_viewer_stream_token
from core.documents.viewer.models import OfficeViewerSaveTokenClaims, OfficeViewerStreamTokenClaims
from core.files.s3_client import S3ClientFactory
from core.logging import get_logger

logger = get_logger(__name__)
router = APIRouter(tags=["office-viewer"])


@router.get("/viewer-stream")
async def viewer_stream(
    container: ContainerDep,
    token: Annotated[str, Query(description="JWT office_view")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        claims = decode_viewer_stream_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise HTTPException(status_code=401, detail="Недействительный viewer token") from exc
    await _authorize_viewer_claims(container, claims)
    meta = await container.file_processor.get_file_record(claims.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != claims.company_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        body = await s3.download_bytes(meta.s3_key)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        logger.warning(
            "viewer-stream: S3 error file_id=%s bucket=%s key=%s code=%s",
            claims.file_id,
            meta.s3_bucket,
            meta.s3_key,
            code,
        )
        raise HTTPException(status_code=502, detail=f"S3 не отдал объект: {code}") from exc
    finally:
        await s3.close()
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
    container: ContainerDep,
    request: Request,
    token: Annotated[str, Query(description="JWT office_view")],
) -> HTMLResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        claims = decode_viewer_stream_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise HTTPException(status_code=401, detail="Недействительный viewer token") from exc
    await _authorize_viewer_claims(container, claims)
    meta = await container.file_processor.get_file_record(claims.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    base = browser_public_base_url(request)
    stream_url = viewer_stream_url(
        base_url=base,
        handler=claims.handler,
        binding_kind=claims.binding_kind,
        binding_id=claims.binding_id,
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
            binding_kind=claims.binding_kind,
            binding_id=claims.binding_id,
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
    container: ContainerDep,
    request: Request,
    token: Annotated[str, Query(description="JWT office_view_save")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office не настроен")
    try:
        claims = decode_viewer_save_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as exc:
        raise HTTPException(status_code=401, detail="Недействительный viewer save token") from exc
    await _authorize_viewer_claims(container, claims)
    body = await request.body()
    if len(body) == 0:
        raise HTTPException(status_code=400, detail="Пустое тело сохранения")
    if len(body) > TEXT_MAX_EDIT_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Размер текста превышает лимит {TEXT_MAX_EDIT_BYTES} байт",
        )
    meta = await container.file_processor.get_file_record(claims.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Файл не найден")
    if meta.company_id != claims.company_id:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    content_type = meta.content_type or "text/plain"
    normalized_content_type = content_type.split(";", 1)[0].strip()
    digest = hashlib.sha256(body).hexdigest()
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        _ = await s3.upload_bytes(
            data=body,
            key=meta.s3_key,
            content_type=normalized_content_type,
            public=meta.is_public,
        )
    finally:
        await s3.close()
    updated_meta = meta.model_copy(
        update={"file_size": len(body), "checksum": digest},
    )
    _ = await container.file_processor.file_repository.set(updated_meta)
    return Response(status_code=204)


async def _authorize_viewer_claims(
    container: OfficeContainer,
    claims: OfficeViewerStreamTokenClaims | OfficeViewerSaveTokenClaims,
) -> None:
    if claims.public_link_token_hash is not None:
        binding_row = await container.access_repository.get_binding_by_link_token_hash(
            claims.public_link_token_hash,
        )
        if binding_row is None:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        if binding_row.binding_id != claims.binding_id or binding_row.file_id != claims.file_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        if binding_row.company_id != claims.company_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        if binding_row.link_permission == "view" and isinstance(claims, OfficeViewerSaveTokenClaims):
            raise HTTPException(status_code=403, detail="Сохранение запрещено")
        return

    if claims.binding_kind == "document":
        binding_row = await container.document_binding_repository.get_by_binding_and_company(
            claims.binding_id,
            claims.company_id,
        )
        if binding_row is None or binding_row.file_id != claims.file_id:
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        return
    if claims.binding_kind == "file":
        if claims.binding_id != file_viewer_binding_id(claims.file_id):
            raise HTTPException(status_code=403, detail="Доступ запрещён")
        return
    raise HTTPException(status_code=403, detail="Доступ запрещён")
