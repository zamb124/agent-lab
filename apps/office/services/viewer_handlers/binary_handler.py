"""Binary/download viewer handler."""

from __future__ import annotations

from typing import ClassVar

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import download_url_for_context
from core.documents.viewer.models import (
    BinaryOpenPayload,
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
)
from core.files.models import FileRecord


class BinaryViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "binary"

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities:
        _ = file_record
        _ = integration_configured
        return DocumentOpenCapabilities(
            view=True,
            edit=False,
            preview=False,
            sync_on_close=False,
            download=True,
            server_mutations=False,
        )

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        content_type = ctx.file_record.content_type or "application/octet-stream"
        normalized = content_type.split(";", 1)[0].strip()
        download_url = download_url_for_context(ctx)
        if download_url is None:
            raise ValueError("download_url обязателен для binary viewer")
        caps = self.capabilities(file_record=ctx.file_record, integration_configured=True)
        return DocumentOpenConfigResponse(
            handler="binary",
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=normalized,
            file_category=ctx.file_category,
            download_url=download_url,
            capabilities=caps,
            binary=BinaryOpenPayload(
                download_url=download_url,
                content_type=normalized,
                file_size=ctx.file_record.file_size,
            ),
        )
