"""
BFF OnlyOffice: протокольные хендлеры (публичные ссылки, скачивание для Document Server,
callback) и REST-зеркала `op_*` редактора.
"""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from botocore.exceptions import ClientError
from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from apps.office.api.commands import router as office_commands_router
from apps.office.api.data_tables import router as office_data_tables_router
from apps.office.api.viewer_routes import router as office_viewer_router
from apps.office.config import get_office_settings
from apps.office.di import Di
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
from apps.office.models.link import DocumentLink
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
from core.files.models import FileRecord
from core.files.object_store.gate import FileGate
from core.files.object_store.principals import SignedFileGrant
from core.http import get_httpx_client
from core.logging import get_logger
from core.middleware.auth.company_resolver import build_service_base_url
from core.types import JsonObject, parse_json_object, require_json_object
from core.websocket import WsCommandError, raise_invalid, raise_not_found
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
    di: Di,
    request: Request,
) -> OfficeEditorConfigResponse:
    return await op_editor_file_config(
        OfficeEditorConfigPayload(file_id=file_id, public_origin=build_service_base_url(request)),
        user=require_context().user,
        di=di,
    )


@router.post("/files/{file_id}/sync", response_model=OfficeFileEditorSyncResponse)
async def sync_file_editor_state(
    file_id: str,
    di: Di,
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
        di=di,
    )


@router.post(
    "/documents/{file_id}/sync",
    response_model=OfficeDocumentEditorSessionResponse,
)
async def sync_document_editor_state(
    file_id: str,
    di: Di,
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
        di=di,
    )


@router.get(
    "/documents/{file_id}/editor-config",
    response_model=OfficeEditorConfigResponse,
)
async def editor_config(
    file_id: str,
    di: Di,
    request: Request,
) -> OfficeEditorConfigResponse:
    return await op_editor_document_config(
        OfficeEditorConfigPayload(file_id=file_id, public_origin=build_service_base_url(request)),
        user=require_context().user,
        di=di,
    )


@router.get("/shares/{token}", response_model=OfficeDocumentShareResolveResponse)
async def resolve_document_share(
    token: str, di: Di
) -> OfficeDocumentShareResolveResponse:
    return await op_document_share_resolve(
        OfficeDocumentShareResolvePayload(token=token),
        user=require_context().user,
        di=di,
    )


@router.get("/public/resolve/{token}", response_model=OfficePublicResolveResponse)
async def public_resolve(token: str, di: Di) -> OfficePublicResolveResponse:
    try:
        target = await di.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise_not_found(exc)
    return await di.office_access_service.build_public_resolve(target)


@router.get("/public/open/{token}", response_model=OfficeEditorConfigResponse)
async def public_open(
    token: str,
    di: Di,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        target = await di.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise_not_found(exc)
    if target.kind != "binding" or target.binding is None:
        raise WsCommandError("ws_invalid_payload", "Open the file via a direct link", error_code="ws_invalid_payload")
    meta = await di.files_service.get_optional(target.binding.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    if meta.company_id != target.binding.company_id:
        raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    try:
        return await di.viewer_service.open_config_for_public_link(
            public_origin=build_service_base_url(request),
            target=target,
            file_record=meta,
        )
    except ValueError as exc:
        raise_invalid(exc)


@router.get("/public/catalog/{token}/items", response_model=OfficePublicCatalogItemsResponse)
async def public_catalog_items(
    token: str, di: Di
) -> OfficePublicCatalogItemsResponse:
    try:
        target = await di.office_access_service.resolve_public_token(token)
    except ValueError as exc:
        raise_not_found(exc)
    try:
        return await di.office_access_service.list_public_catalog_items(target)
    except ValueError as exc:
        raise_invalid(exc)


@router.get(
    "/public/catalog/{token}/files/{file_id}/open",
    response_model=OfficeEditorConfigResponse,
)
async def public_catalog_binding_open(
    token: str,
    file_id: str,
    di: Di,
    request: Request,
) -> OfficeEditorConfigResponse:
    try:
        catalog_target = await di.office_access_service.resolve_public_token(token)
        binding = await di.office_access_service.resolve_public_catalog_binding_open(
            catalog_target,
            file_id,
        )
    except ValueError as exc:
        raise_not_found(exc)
    file_link = await DocumentLink.for_target("file", binding.file_id)
    if file_link is None or not file_link.enabled or file_link.token_hash is None:
        raise WsCommandError("forbidden", "File public link is not configured", error_code="forbidden")
    binding_target = PublicLinkTarget(
        kind="binding",
        catalog=None,
        binding=binding,
        token_hash=file_link.token_hash,
    )
    meta = await di.files_service.get_optional(binding.file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    try:
        return await di.viewer_service.open_config_for_public_link(
            public_origin=build_service_base_url(request),
            target=binding_target,
            file_record=meta,
        )
    except ValueError as exc:
        raise_invalid(exc)


@router.get("/office-download")
async def office_download(
    di: Di,
    token: Annotated[str, Query(description="JWT office_dl")],
) -> Response:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise WsCommandError("unavailable", "office is not configured", error_code="unavailable")
    try:
        claims = decode_download_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise WsCommandError("unauthorized", "Invalid download token", error_code="unauthorized") from e
    file_id = claims.file_id
    company_id = claims.company_id
    viewer_scope = claims.viewer_scope
    if viewer_scope == "catalog":
        binding_row = await FileRecord.for_company(
            file_id,
            company_id,
        )
        if binding_row is None:
            raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    elif viewer_scope != "file":
        raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    meta = await di.files_service.get_optional(file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code="not_found")
    if meta.company_id != company_id:
        raise WsCommandError("forbidden", "Access denied", error_code="forbidden")
    try:
        handle = await FileGate().open_record(
            meta,
            SignedFileGrant(file_id=file_id, company_id=company_id),
        )
        body = await handle.read_bytes()
    except ClientError as e:
        code = e.response["Error"]["Code"]
        logger.warning(
            "office.download.s3.error.file_id",
            file_id=file_id,
            storage_id=meta.storage_id,
            key=meta.s3_key,
            code=code,
        )
        raise WsCommandError(
            "upstream",
            f"S3 did not return the object: {code}",
            error_code="upstream",
        ) from e
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
    di: Di,
    token: Annotated[str, Query(description="JWT office_cb")],
) -> OnlyOfficeCallbackResponse:
    integ = get_office_settings().office
    if not integ.jwt_secret.strip():
        raise WsCommandError("unavailable", "office is not configured", error_code="unavailable")
    try:
        ctx_cb = decode_callback_context_token(token, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise WsCommandError("unauthorized", "Invalid callback token", error_code="unauthorized") from e
    file_id = ctx_cb.file_id
    company_id = ctx_cb.company_id
    viewer_scope = ctx_cb.viewer_scope

    try:
        raw_body = await request.body()
        body = parse_json_object(raw_body, "OnlyOffice callback body") if raw_body else {}
    except ValueError as exc:
        raise WsCommandError("ws_invalid_payload", "Callback body must be a JSON object", error_code="ws_invalid_payload") from exc

    auth = request.headers.get("Authorization")
    bearer = ""
    if auth and auth.startswith("Bearer "):
        bearer = auth[7:].strip()
    else:
        body_token = body.get("token")
        if isinstance(body_token, str) and body_token.strip() != "":
            bearer = body_token.strip()
    if not bearer:
        raise WsCommandError(
            "unauthorized",
            "OnlyOffice JWT is required in Authorization: Bearer or body.token",
            error_code="unauthorized",
        )
    try:
        token_payload = decode_callback_authorization(bearer, integ.jwt_secret)
    except OnlyOfficeJwtError as e:
        raise WsCommandError("unauthorized", "Invalid callback JWT", error_code="unauthorized") from e
    payload = _onlyoffice_request_payload(token_payload, body)

    namespace = ctx_cb.namespace or ""
    status_raw = payload.get("status")
    if status_raw is None:
        raise WsCommandError("ws_invalid_payload", "Callback status is required", error_code="ws_invalid_payload")
    if not isinstance(status_raw, str | int):
        raise WsCommandError("ws_invalid_payload", "Callback status must be an integer", error_code="ws_invalid_payload")
    try:
        status_int = int(status_raw)
    except ValueError:
        raise WsCommandError("ws_invalid_payload", "Callback status must be an integer", error_code="ws_invalid_payload") from None
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
            raise WsCommandError("ws_invalid_payload", "Callback has no url for save", error_code="ws_invalid_payload")
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
        document_binding: FileRecord | None = None

        if viewer_scope == "catalog":
            document_binding = await FileRecord.for_company(
                file_id,
                company_id,
            )
            if document_binding is None:
                logger.error("office.onlyoffice.callback.company", file_id=file_id, company=company_id)
                raise WsCommandError("not_found", "Binding not found", error_code="not_found")
            notification_user_id = document_binding.uploaded_by
            notification_message = document_binding.original_name
            notification_action_url = f"/documents/edit/{file_id}"
            notification_data = {"file_id": file_id, "company_id": company_id}
        elif viewer_scope != "file":
            raise WsCommandError("ws_invalid_payload", "Invalid OnlyOffice viewer_scope", error_code="ws_invalid_payload")

        meta = await di.files_service.get_optional(file_id)
        if meta is None:
            raise WsCommandError("not_found", "File not found", error_code="not_found")
        if meta.company_id != company_id:
            raise WsCommandError("forbidden", "File does not belong to the company", error_code="forbidden")

        async with get_httpx_client(timeout=120.0) as client:
            r = await client.get(url)
            _ = r.raise_for_status()
            new_bytes = r.content
        previous_size = meta.file_size
        previous_checksum = meta.checksum
        updated = await di.files_service.replace_content(
            meta,
            new_bytes,
            content_type=meta.content_type or "application/octet-stream",
            expected_checksum=meta.checksum,
        )
        digest = updated.checksum or ""
        if document_binding is not None:
            try:
                await index_binding_if_catalog_enabled_with_job_context(
                    di,
                    document_binding,
                    company_id=company_id,
                    workspace_namespace=namespace,
                    user_id=document_binding.uploaded_by or "",
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
