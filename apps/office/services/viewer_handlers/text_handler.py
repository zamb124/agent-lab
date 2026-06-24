"""Text/code viewer handler with optional edit."""

from __future__ import annotations

from typing import ClassVar

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import (
    download_url_for_context,
    viewer_save_url,
    viewer_stream_url,
)
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    TextOpenPayload,
)
from core.files.models import FileRecord

TEXT_MAX_EDIT_BYTES = 512_000


class TextViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "text"

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities:
        _ = integration_configured
        editable = file_record.file_size <= TEXT_MAX_EDIT_BYTES
        return DocumentOpenCapabilities(
            view=True,
            edit=editable,
            preview=True,
            sync_on_close=editable,
            download=True,
            server_mutations=False,
        )

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        binding_kind = "file" if ctx.binding_kind == "file" else "document"
        content_type = ctx.file_record.content_type or "text/plain"
        normalized = content_type.split(";", 1)[0].strip()
        caps = self.capabilities(file_record=ctx.file_record, integration_configured=True)
        can_edit = caps.edit and ctx.link_permission == "edit"
        stream_url = viewer_stream_url(
            base_url=ctx.browser_public_base_url,
            handler="text",
            binding_kind=binding_kind,
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            company_id=ctx.company_id,
            content_type=normalized,
            secret=ctx.jwt_secret,
            ttl_seconds=ctx.download_token_ttl_seconds,
            edit_mode=can_edit,
            public_link_token_hash=ctx.public_link_token_hash,
        )
        save_url = ""
        if can_edit:
            save_url = viewer_save_url(
                base_url=ctx.browser_public_base_url,
                binding_kind=binding_kind,
                binding_id=ctx.binding_id,
                file_id=ctx.file_record.file_id,
                company_id=ctx.company_id,
                secret=ctx.jwt_secret,
                ttl_seconds=ctx.download_token_ttl_seconds,
                public_link_token_hash=ctx.public_link_token_hash,
            )
        return DocumentOpenConfigResponse(
            handler="text",
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=normalized,
            file_category=ctx.file_category,
            download_url=download_url_for_context(ctx) if caps.download else None,
            capabilities=caps,
            text=TextOpenPayload(
                stream_url=stream_url,
                save_url=save_url,
                content_type=normalized,
                edit_mode=can_edit,
                max_edit_bytes=TEXT_MAX_EDIT_BYTES,
            ),
        )
