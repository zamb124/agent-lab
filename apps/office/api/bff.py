"""
BFF OnlyOffice: протокольные хендлеры (публичные ссылки, скачивание для Document Server,
callback) и REST-зеркала `op_*` редактора.
"""

from __future__ import annotations

import hashlib
from typing import Annotated
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from apps.office.api.commands import router as office_commands_router
from apps.office.api.data_tables import router as office_data_tables_router
from apps.office.api.viewer_routes import router as office_viewer_router
from apps.office.config import get_office_settings
from apps.office.db.models import OfficeDocumentBinding
from apps.office.dependencies import ContainerDep
from apps.office.events import OFFICE_DOCUMENT_SAVED
from apps.office.models.api import (
    OfficeDocumentEditorSessionResponse,
    OfficeDocumentShareResolveResponse,
    OfficeDocumentSyncRequest,
    OfficeEditorConfigResponse,
    OfficeFileEditorSyncResponse,
    OfficePublicCatalogItemsResponse,
    OfficePublicResolveResponse,
    OnlyOfficeCallbackResponse,
)
from apps.office.realtime.editor_operations import (
    OfficeDocumentShareResolvePayload,
    OfficeEditorConfigPayload,
    OfficeEditorSyncPayload,
    op_document_share_resolve,
    op_editor_document_config,
    op_editor_document_sync,
    op_editor_file_config,
    op_editor_file_sync,
)
from apps.office.realtime.operations import (
    index_binding_if_catalog_enabled_with_job_context,
    raise_from_catalog_rag_value_error,
    raise_from_service_client,
)
from apps.office.services.callback_dedupe import try_claim_onlyoffice_callback
from apps.office.services.callback_token import decode_callback_context_token
from apps.office.services.office_access_service import PublicLinkTarget
from apps.office.services.onlyoffice_jwt import (
    decode_callback_authorization,
    decode_download_token,
)
from core.clients.onlyoffice import OnlyOfficeJwtError
from core.clients.service_client import ServiceClientError
from core.config import get_settings
from core.context import require_context
from core.events import publish_event_to_user
from core.files.s3_client import S3ClientFactory
from core.http import get_httpx_client
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.types import JsonObject, parse_json_object, require_json_object
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)
router = APIRouter(tags=["office-bff"])
router.include_router(office_commands_router)
router.include_router(office_viewer_router)
router.include_router(office_data_tables_router)


def _office_inline_content_disposition(original_name: str) -> str:
    name = (original_name or "document").replace("\r", "").replace("\n", "")[:800]
    ascii_fallback = name.encode("ascii", "ignore").decode("ascii").strip() or "document"
    ascii_fallback = ascii_fallback.replace("\\", "_").replace('"', "'")[:200]
    encoded = quote(name, safe="")
    return f"inline; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded}"


def _onlyoffice_request_payload(token_payload: JsonObject, body: JsonObject) -> JsonObject:
    """
    ONLYOFFICE can sign callback/command parameters directly or wrap them in {"payload": {...}}.
    Header JWT uses the wrapper in current docs; body JWT often signs the parameters directly.
    """
    wrapped = token_payload.get("payload")
    if wrapped is not None:
        return require_json_object(wrapped, "OnlyOffice callback payload")
    if "status" in token_payload or "url" in token_payload or "key" in token_payload:
        return token_payload
    if "status" in body or "url" in body or "key" in body:
        return body
    return token_payload


@router.get("/files/{file_id}/editor-config", response_model=OfficeEditorConfigResponse)
async def file_editor_config(
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    return await op_editor_file_config(
        OfficeEditorConfigPayload(file_id=file_id, public_origin=build_service_base_url(request)),
        user=require_context().user,
        container=container,
    )


@router.post("/files/{file_id}/sync", response_model=OfficeFileEditorSyncResponse)
async def sync_file_editor_state(
    file_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeFileEditorSyncResponse:
    sync_options = body if body is not None else OfficeDocumentSyncRequest()
    return await op_editor_file_sync(
        OfficeEditorSyncPayload(
            file_id=file_id,
            close=sync_options.close,
            settle_ms=sync_options.settle_ms,
            dirty=sync_options.dirty,
        ),
        user=require_context().user,
        container=container,
    )


@router.post(
    "/documents/{file_id}/sync",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def sync_document_editor_state(
    file_id: str,
    container: ContainerDep,
    body: OfficeDocumentSyncRequest | None = None,
) -> OfficeDocumentEditorSessionResponse:
    sync_options = body if body is not None else OfficeDocumentSyncRequest()
    return await op_editor_document_sync(
        OfficeEditorSyncPayload(
            file_id=file_id,
            close=sync_options.close,
            settle_ms=sync_options.settle_ms,
            dirty=sync_options.dirty,
        ),
        user=require_context().user,
        container=container,
    )


@router.get(
    "/documents/{file_id}/editor-config",
    response_model=OfficeEditorConfigResponse,
)
async def editor_config(
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    return await op_editor_document_config(
        OfficeEditorConfigPayload(file_id=file_id, public_origin=build_service_base_url(request)),
        user=require_context().user,
        container=container,
    )


@router.get("/shares/{token}", response_model=OfficeDocumentShareResolveResponse)
async def resolve_document_share(
    token: str, container: ContainerDep
) -> OfficeDocumentShareResolveResponse:
    return await op_document_share_resolve(
        OfficeDocumentShareResolvePayload(token=token),
        user=require_context().user,
        container=container,
    )


@router.get("/public/resolve/{token}", response_model=OfficePublicResolveResponse)
async def public_resolve(token: str, container: ContainerDep) -> OfficePublicResolveResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await container.office_access_service.build_public_resolve(target)


@router.get("/public/open/{token}", response_model=OfficeEditorConfigResponse)
async def public_open(
    token: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if target.kind != "binding" or target.binding is None:
        raise HTTPException(status_code=400, detail="Open the file via a direct link")
    meta = await container.files_service.get_optional(target.binding.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found")
    if meta.company_id != target.binding.company_id:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        return await container.viewer_service.open_config_for_public_link(
            public_origin=build_service_base_url(request),
            target=target,
            file_record=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/public/catalog/{token}/items", response_model=OfficePublicCatalogItemsResponse)
async def public_catalog_items(
    token: str, container: ContainerDep
) -> OfficePublicCatalogItemsResponse:
    try:
        target = await container.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        return await container.office_access_service.list_public_catalog_items(target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/public/catalog/{token}/files/{file_id}/open",
    response_model=OfficeEditorConfigResponse,
)
async def public_catalog_binding_open(
    token: str,
    file_id: str,
    container: ContainerDep,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        catalog_target = await container.office_access_service.resolve_public_token(token)
        binding = await container.office_access_service.resolve_public_catalog_binding_open(
            catalog_target,
            file_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    binding_target = PublicLinkTarget(
        kind="binding",
        catalog=None,
        binding=binding,
        token_hash=binding.link_token_hash or "",
    )
    if binding.link_token_hash is None:
        raise HTTPException(status_code=403, detail="File public link is not configured")
    meta = await container.files_service.get_optional(binding.file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found")
    try:
        return await container.viewer_service.open_config_for_public_link(
            public_origin=build_service_base_url(request),
            target=binding_target,
            file_record=meta,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/office-download")
async def office_download(
    container: ContainerDep,
    token: Annotated[str, Query(description="JWT office_dl")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office is not configured")
    try:
        claims = decode_download_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Invalid download token") from e
    file_id = claims.file_id
    company_id = claims.company_id
    viewer_scope = claims.viewer_scope
    if viewer_scope == "catalog":
        binding_row = await container.document_binding_repository.get_by_file_and_company(
            file_id,
            company_id,
        )
        if binding_row is None:
            raise HTTPException(status_code=403, detail="Access denied")
    elif viewer_scope != "file":
        raise HTTPException(status_code=403, detail="Access denied")
    meta = await container.files_service.get_optional(file_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="File not found")
    if meta.company_id != company_id:
        raise HTTPException(status_code=403, detail="Access denied")
    s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
    try:
        try:
            body = await s3.download_bytes(meta.s3_key)
        except ClientError as e:
            code = e.response["Error"]["Code"]
            logger.warning(
                "office.download.s3.error.file_id",
                file_id=file_id,
                bucket=meta.s3_bucket,
                key=meta.s3_key,
                code=code,
            )
            raise HTTPException(
                status_code=502,
                detail=f"S3 did not return the object: {code}",
            ) from e
    finally:
        await s3.close()
    ct = meta.content_type or "application/octet-stream"
    return Response(
        content=body,
        media_type=ct,
        headers={"Content-Disposition": _office_inline_content_disposition(meta.original_name)},
    )


@router.post(
    "/onlyoffice/callback",
    response_model=OnlyOfficeCallbackResponse,
)
async def onlyoffice_callback(
    request: Request,
    container: ContainerDep,
    token: Annotated[str, Query(description="JWT office_cb")],
) -> OnlyOfficeCallbackResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise HTTPException(status_code=503, detail="office is not configured")
    try:
        ctx_cb = decode_callback_context_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Invalid callback token") from e
    file_id = ctx_cb.file_id
    company_id = ctx_cb.company_id
    viewer_scope = ctx_cb.viewer_scope

    try:
        raw_body = await request.body()
        body = parse_json_object(raw_body, "OnlyOffice callback body") if raw_body else {}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Callback body must be a JSON object") from exc

    auth = request.headers.get("Authorization")
    bearer = ""
    if auth and auth.startswith("Bearer "):
        bearer = auth[7:].strip()
    else:
        body_token = body.get("token")
        if isinstance(body_token, str) and body_token.strip() != "":
            bearer = body_token.strip()
    if not bearer:
        raise HTTPException(
            status_code=401,
            detail="OnlyOffice JWT is required in Authorization: Bearer or body.token",
        )
    try:
        token_payload = decode_callback_authorization(bearer, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise HTTPException(status_code=401, detail="Invalid callback JWT") from e
    payload = _onlyoffice_request_payload(token_payload, body)

    namespace = ctx_cb.namespace or ""
    status_raw = payload.get("status")
    if status_raw is None:
        raise HTTPException(status_code=400, detail="Callback status is required")
    if not isinstance(status_raw, str | int):
        raise HTTPException(status_code=400, detail="Callback status must be an integer")
    try:
        status_int = int(status_raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Callback status must be an integer") from None
    logger.info(
        "office.onlyoffice.callback.received.file_id.company_id",
        file_id=file_id,
        company_id=company_id,
        namespace=namespace,
        status=status_int,
        key=payload.get('key'),
    )

    if status_int in (2, 6):
        url = payload.get("url")
        if not url or not isinstance(url, str):
            raise HTTPException(status_code=400, detail="Callback has no url for save")
        redis_url = get_settings().database.redis_url
        claimed = await try_claim_onlyoffice_callback(
            redis_url,
            file_id,
            status_int,
            url,
        )
        if not claimed:
            logger.info("office.onlyoffice.callback.file_id.status", file_id=file_id, status=status_int)
            return OnlyOfficeCallbackResponse(error=0)

        notification_user_id: str | None = None
        notification_title = "Документ сохранён"
        notification_message = ""
        notification_action_url: str | None = None
        notification_data: JsonObject = {}
        document_binding: OfficeDocumentBinding | None = None

        if viewer_scope == "catalog":
            document_binding = await container.document_binding_repository.get_by_file_and_company(
                file_id,
                company_id,
            )
            if document_binding is None:
                logger.error("office.onlyoffice.callback.company", file_id=file_id, company=company_id)
                raise HTTPException(status_code=404, detail="Binding not found")
            notification_user_id = document_binding.created_by_user_id
            notification_message = document_binding.title
            notification_action_url = f"/documents/edit/{file_id}"
            notification_data = {"file_id": file_id, "company_id": company_id}
        elif viewer_scope != "file":
            raise HTTPException(status_code=400, detail="Invalid OnlyOffice viewer_scope")

        meta = await container.files_service.get_optional(file_id)
        if meta is None:
            raise HTTPException(status_code=404, detail="File not found")
        if meta.company_id != company_id:
            raise HTTPException(status_code=403, detail="File does not belong to the company")

        async with get_httpx_client(timeout=120.0) as client:
            r = await client.get(url)
            _ = r.raise_for_status()
            new_bytes = r.content
        previous_size = meta.file_size
        previous_checksum = meta.checksum
        s3 = S3ClientFactory.create_client_for_bucket(meta.s3_bucket)
        try:
            _ = await s3.upload_bytes(
                data=new_bytes,
                key=meta.s3_key,
                content_type=meta.content_type or "application/octet-stream",
                public=meta.is_public,
            )
        finally:
            await s3.close()
        digest = hashlib.sha256(new_bytes).hexdigest()
        updated = meta.model_copy(
            update={"file_size": len(new_bytes), "checksum": digest},
        )
        _ = await container.files_service.save(updated)
        if document_binding is not None:
            try:
                await index_binding_if_catalog_enabled_with_job_context(
                    container,
                    document_binding,
                    company_id=company_id,
                    workspace_namespace=namespace,
                    user_id=document_binding.created_by_user_id,
                )
            except ServiceClientError as exc:
                raise_from_service_client("rag", exc)
            except ValueError as exc:
                raise_from_catalog_rag_value_error(exc)
        logger.info(
            "office.onlyoffice.callback.saved.viewer_scope.file_id",
            viewer_scope=viewer_scope,
            file_id=file_id,
            status=status_int,
            bytes=len(new_bytes),
            old_size=previous_size,
            old_checksum=previous_checksum,
            new_checksum=digest,
        )

        if notification_user_id is not None:
            await publish_event_to_user(
                notification_user_id,
                OFFICE_DOCUMENT_SAVED,
                {
                    "file_id": file_id,
                    "company_id": company_id,
                    "title": notification_message,
                },
                company_id=company_id,
            )
            await notify_user(
                notification_user_id,
                Notification(
                    type=NotificationType.OFFICE_DOCUMENT_SAVED,
                    title=notification_title,
                    message=notification_message,
                    service="office",
                    priority="normal",
                    action_url=notification_action_url,
                    data=notification_data,
                ),
            )

    return OnlyOfficeCallbackResponse(error=0)
