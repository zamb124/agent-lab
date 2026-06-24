"""OnlyOffice viewer handler."""

from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import quote

from apps.office.services.callback_token import encode_callback_context_token
from apps.office.services.document_type import (
    onlyoffice_file_type_for_binding,
    resolve_onlyoffice_document_type_for_editor,
)
from apps.office.services.file_binding_metadata import onlyoffice_document_type_for_binding_row
from apps.office.services.onlyoffice_jwt import encode_download_token, encode_editor_config
from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._office_customization import (
    onlyoffice_editor_customization_payload,
)
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    OnlyOfficeOpenPayload,
)
from core.files.models import FileRecord
from core.types import JsonObject


def onlyoffice_document_key(binding_id: str, checksum: str | None) -> str:
    safe_checksum = re.sub(r"[^a-zA-Z0-9_-]", "", checksum or "")[:24]
    if not safe_checksum:
        return binding_id
    return f"{binding_id}_{safe_checksum}"


class OnlyOfficeViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "onlyoffice"

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities:
        _ = file_record
        if not integration_configured:
            raise ValueError("office_integration_not_configured")
        return DocumentOpenCapabilities(
            view=True,
            edit=True,
            preview=True,
            sync_on_close=True,
            download=True,
            server_mutations=True,
        )

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        stored_onlyoffice_type = onlyoffice_document_type_for_binding_row(
            onlyoffice_document_type=ctx.onlyoffice_document_type,
            original_name=ctx.file_record.original_name,
        )
        base = ctx.callback_public_base_url.rstrip("/")
        binding_kind = "file" if ctx.binding_kind == "file" else "document"
        dl = encode_download_token(
            file_id=ctx.file_record.file_id,
            company_id=ctx.company_id,
            binding_id=ctx.binding_id,
            binding_kind=binding_kind,
            secret=ctx.jwt_secret,
            ttl_seconds=ctx.download_token_ttl_seconds,
        )
        download_url = f"{base}/documents/api/v1/office-download?token={quote(dl, safe='')}"
        cb_ctx = encode_callback_context_token(
            binding_id=ctx.binding_id,
            company_id=ctx.company_id,
            namespace=ctx.namespace,
            file_id=ctx.file_record.file_id if binding_kind == "file" else None,
            binding_kind=binding_kind,
            secret=ctx.jwt_secret,
            ttl_seconds=3600,
        )
        callback_url = f"{base}/documents/api/v1/onlyoffice/callback?token={quote(cb_ctx, safe='')}"
        doc_key = onlyoffice_document_key(ctx.binding_id, ctx.file_record.checksum)
        editor_document_type = resolve_onlyoffice_document_type_for_editor(
            stored_onlyoffice_type,
            ctx.file_record.original_name,
        )
        file_type = onlyoffice_file_type_for_binding(editor_document_type, ctx.file_record.original_name)
        can_edit = ctx.link_permission == "edit"
        editor_mode = "edit" if can_edit else "view"
        document_permissions: JsonObject = {
            "comment": can_edit,
            "copy": True,
            "download": True,
            "edit": can_edit,
            "fillForms": can_edit,
            "modifyContentControl": can_edit,
            "modifyFilter": can_edit,
            "print": True,
            "review": can_edit,
        }
        config: JsonObject = {
            "type": "desktop",
            "width": "100%",
            "height": "100%",
            "document": {
                "fileType": file_type,
                "key": doc_key,
                "title": ctx.title,
                "url": download_url,
                "permissions": document_permissions,
            },
            "documentType": editor_document_type,
            "editorConfig": {
                "mode": editor_mode,
                "callbackUrl": callback_url if can_edit else "",
                "user": {"id": ctx.user_id, "name": ctx.user_name},
                "lang": ctx.editor_lang,
                "coEditing": {"mode": "fast"},
                "customization": onlyoffice_editor_customization_payload(),
            },
        }
        token = encode_editor_config(config, ctx.jwt_secret)
        content_type = ctx.file_record.content_type or "application/octet-stream"
        caps = self.capabilities(
            file_record=ctx.file_record,
            integration_configured=True,
        )
        if not can_edit:
            caps = caps.model_copy(
                update={
                    "edit": False,
                    "sync_on_close": False,
                    "server_mutations": False,
                },
            )
        return DocumentOpenConfigResponse(
            handler="onlyoffice",
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=content_type.split(";", 1)[0].strip(),
            file_category=ctx.file_category,
            onlyoffice_document_type=editor_document_type,
            download_url=download_url,
            capabilities=caps,
            onlyoffice=OnlyOfficeOpenPayload(
                document_server_url=ctx.browser_document_server_url,
                token=token,
            ),
        )
