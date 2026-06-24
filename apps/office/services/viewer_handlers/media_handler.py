"""Audio/video viewer handler."""

from __future__ import annotations

from typing import ClassVar

from apps.office.services.viewer_context import ViewerOpenContext
from apps.office.services.viewer_handlers._urls import download_url_for_context, viewer_stream_url
from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    MediaOpenPayload,
    MediaViewerKind,
)
from core.documents.viewer.resolver import file_category_to_enum
from core.files.models import FileRecord
from core.files.types import FileCategory


class MediaViewerHandler:
    handler_id: ClassVar[DocumentViewerHandlerId] = "media"

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities:
        _ = file_record
        _ = integration_configured
        return DocumentOpenCapabilities(
            view=True,
            edit=False,
            preview=True,
            sync_on_close=False,
            download=True,
            server_mutations=False,
        )

    def _media_kind(self, file_category: str) -> MediaViewerKind:
        category = file_category_to_enum(file_category)
        if category == FileCategory.VIDEO:
            return "video"
        return "audio"

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse:
        binding_kind = "file" if ctx.binding_kind == "file" else "document"
        content_type = ctx.file_record.content_type or "application/octet-stream"
        normalized = content_type.split(";", 1)[0].strip()
        kind = self._media_kind(ctx.file_category)
        stream_url = viewer_stream_url(
            base_url=ctx.browser_public_base_url,
            handler="media",
            binding_kind=binding_kind,
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            company_id=ctx.company_id,
            content_type=normalized,
            secret=ctx.jwt_secret,
            ttl_seconds=ctx.download_token_ttl_seconds,
            public_link_token_hash=ctx.public_link_token_hash,
        )
        caps = self.capabilities(file_record=ctx.file_record, integration_configured=True)
        return DocumentOpenConfigResponse(
            handler="media",
            binding_id=ctx.binding_id,
            file_id=ctx.file_record.file_id,
            title=ctx.title,
            original_name=ctx.file_record.original_name,
            content_type=normalized,
            file_category=ctx.file_category,
            download_url=download_url_for_context(ctx) if caps.download else None,
            capabilities=caps,
            media=MediaOpenPayload(
                stream_url=stream_url,
                content_type=normalized,
                kind=kind,
            ),
        )
