"""Открытие OnlyOffice-редактора, синхронизация открытых сессий и ссылки-шаринг.

`public_origin` (`scheme://host[:port]` браузера пользователя) приходит в payload:
REST-зеркало берёт его из запроса (`build_service_base_url`), WS-клиент — из
`window.location.origin`. Из него строятся URL Document Server и скачивания,
которые должен открыть именно браузер, а не внутренняя сеть сервисов.
"""

from __future__ import annotations

import asyncio

from pydantic import Field

from apps.office.db.models import OfficeDocumentBinding
from apps.office.di import Di
from apps.office.models.api import (
    OfficeDocumentEditorSessionResponse,
    OfficeDocumentShareResolveResponse,
    OfficeDocumentSyncRequest,
    OfficeEditorConfigResponse,
    OfficeFileEditorSyncResponse,
)
from apps.office.realtime.operations import (
    ONLYOFFICE_COMMAND_ERROR_DETAILS,
    OfficeFileIdPayload,
    document_mutation_lock,
    drop_open_editor_sessions,
    editor_embed_url,
    force_save_open_editor_if_needed,
    load_binding,
    namespace_scope,
    onlyoffice_document_key,
    require_binding_catalog_access,
    wait_for_file_change_after_forcesave,
)
from apps.office.services.document_type import supports_onlyoffice_viewer
from apps.office.services.file_binding_metadata import resolve_binding_metadata
from core.context import require_context
from core.files.models import FileRecord
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.identity_models import User
from core.request_scope import require_company
from core.websocket import WsCommandError, raise_invalid, raise_not_found

logger = get_logger(__name__)


class OfficeEditorConfigPayload(OfficeFileIdPayload):
    public_origin: str = Field(min_length=1)


class OfficeEditorSyncPayload(OfficeDocumentSyncRequest):
    file_id: str = Field(min_length=1)


class OfficeDocumentShareResolvePayload(StrictBaseModel):
    token: str = Field(min_length=1)


def _content_type_base(file_record: FileRecord) -> str:
    return (file_record.content_type or "application/octet-stream").split(";")[0].strip()


async def _load_company_file(
    di: Di, file_id: str, company_id: str
) -> FileRecord:
    meta = await di.files_service.get_optional(file_id)
    if meta is None:
        raise WsCommandError("not_found", "File not found", error_code='not_found')
    if meta.company_id != company_id:
        raise WsCommandError("forbidden", "File does not belong to the company", error_code='forbidden')
    return meta


def _user_display_name(user: User) -> str:
    if user.name:
        return user.name
    if user.email:
        return user.email
    return user.user_id


async def _sync_open_editor(
    di: Di,
    *,
    file_id: str,
    checksum: str | None,
    file_size: int,
    sync_options: OfficeDocumentSyncRequest,
) -> None:
    """Forcesave открытого редактора и (при close) сброс сессий Document Server."""
    document_key = onlyoffice_document_key(file_id, checksum)
    if sync_options.settle_ms > 0:
        await asyncio.sleep(sync_options.settle_ms / 1000)
    force_code = await force_save_open_editor_if_needed(file_id=file_id, document_key=document_key)
    if sync_options.close and force_code == 4:
        await asyncio.sleep(1.5)
        force_code = await force_save_open_editor_if_needed(
            file_id=file_id, document_key=document_key
        )
    logger.info(
        "office.editor.sync",
        file_id=file_id,
        close=sync_options.close,
        dirty=sync_options.dirty,
        force_code=force_code,
    )
    if sync_options.close and sync_options.dirty is True and force_code in (1, 4):
        detail = ONLYOFFICE_COMMAND_ERROR_DETAILS.get(force_code, "unknown error")
        raise WsCommandError(
            "conflict",
            f"OnlyOffice did not accept pending editor changes yet: error={force_code} ({detail})",
                  error_code='conflict',
              )
    if force_code == 0:
        _ = await wait_for_file_change_after_forcesave(
            di=di,
            file_id=file_id,
            previous_checksum=checksum,
            previous_file_size=file_size,
        )
    if sync_options.close and force_code in (0, 4):
        await drop_open_editor_sessions(file_id=file_id, document_key=document_key)


async def op_editor_file_config(
    payload: OfficeEditorConfigPayload,
    *,
    user: User,
    di: Di,
) -> OfficeEditorConfigResponse:
    """Конфиг редактора для файла Files API вне каталога Documents (chat/flow вложения)."""
    scope = require_company()
    context = require_context()
    meta = await _load_company_file(di, payload.file_id, scope.company_id)
    file_category, onlyoffice_document_type = resolve_binding_metadata(
        meta.original_name, _content_type_base(meta)
    )
    binding = await OfficeDocumentBinding.binding_for_company(
        payload.file_id,
        scope.company_id,
    )
    namespace: str | None = None
    if binding is not None and binding.namespace.strip():
        namespace = binding.namespace
    elif context.active_namespace.strip():
        namespace = context.active_namespace.strip()
    try:
        return await di.viewer_service.open_config_for_file(
            public_origin=payload.public_origin,
            file_record=meta,
            company_id=scope.company_id,
            user_id=user.user_id,
            user_name=_user_display_name(user),
            editor_lang=di.viewer_service.default_editor_lang(context.language),
            file_category=file_category,
            onlyoffice_document_type=onlyoffice_document_type,
            namespace=namespace,
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_editor_document_config(
    payload: OfficeEditorConfigPayload,
    *,
    user: User,
    di: Di,
) -> OfficeEditorConfigResponse:
    scope = await namespace_scope(di)
    context = require_context()
    row = await load_binding(scope, payload.file_id, allow_deleted=True)
    await require_binding_catalog_access(di, row, scope.user_id)
    meta = await _load_company_file(di, row.file_id, scope.company_id)
    try:
        return await di.viewer_service.open_config_for_binding(
            public_origin=payload.public_origin,
            binding=row,
            file_record=meta,
            user_id=user.user_id,
            user_name=_user_display_name(user),
            editor_lang=di.viewer_service.default_editor_lang(context.language),
        )
    except ValueError as exc:
        raise_invalid(exc)


async def op_editor_file_sync(
    payload: OfficeEditorSyncPayload,
    *,
    user: User,
    di: Di,
) -> OfficeFileEditorSyncResponse:
    _ = user
    scope = require_company()
    async with document_mutation_lock(di, payload.file_id):
        meta = await _load_company_file(di, payload.file_id, scope.company_id)
        if supports_onlyoffice_viewer(meta.original_name, _content_type_base(meta)):
            await _sync_open_editor(
                di,
                file_id=payload.file_id,
                checksum=meta.checksum,
                file_size=meta.file_size,
                sync_options=payload,
            )
            meta = await _load_company_file(di, payload.file_id, scope.company_id)
    return OfficeFileEditorSyncResponse(
        file_id=meta.file_id, checksum=meta.checksum, file_size=meta.file_size
    )


async def op_editor_document_sync(
    payload: OfficeEditorSyncPayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentEditorSessionResponse:
    _ = user
    scope = await namespace_scope(di)
    async with document_mutation_lock(di, payload.file_id):
        row = await load_binding(scope, payload.file_id, allow_deleted=True)
        await require_binding_catalog_access(di, row, scope.user_id)
        meta = await _load_company_file(di, row.file_id, scope.company_id)
        if supports_onlyoffice_viewer(meta.original_name, _content_type_base(meta)):
            await _sync_open_editor(
                di,
                file_id=row.file_id,
                checksum=meta.checksum,
                file_size=meta.file_size,
                sync_options=payload,
            )
    return OfficeDocumentEditorSessionResponse(
        file_id=row.file_id,
        catalog_id=row.catalog_id,
        title=row.title,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
        namespace=scope.namespace,
        editor_url=editor_embed_url(row.file_id, scope.namespace),
    )


async def op_document_share_resolve(
    payload: OfficeDocumentShareResolvePayload,
    *,
    user: User,
    di: Di,
) -> OfficeDocumentShareResolveResponse:
    """Метаданные документа по публичному токену ссылки; сам доступ даёт токен, не сессия."""
    _ = user
    try:
        target = await di.office_access_service.resolve_public_token(payload.token)
    except ValueError as exc:
        raise_not_found(exc)
    if target.kind != "binding" or target.binding is None:
        raise WsCommandError("not_found", "Link not found", error_code='not_found')
    row = target.binding
    if row.deleted_at is not None:
        raise WsCommandError("not_found", "Document not found", error_code='not_found')
    if row.link_permission not in ("viewer", "editor"):
        raise WsCommandError(
            "ws_invalid_payload", f"Invalid link_permission: {row.link_permission}",
                  error_code='ws_invalid_payload',
              )
    return OfficeDocumentShareResolveResponse(
        file_id=row.file_id,
        title=row.title,
        permission=row.link_permission,
        file_category=row.file_category,
        onlyoffice_document_type=row.onlyoffice_document_type,
    )
