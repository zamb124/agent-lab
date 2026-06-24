"""Protocol viewer handler для office service."""

from __future__ import annotations

from typing import Protocol

from core.documents.viewer.models import (
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
)
from core.files.models import FileRecord


class ViewerOpenContext(Protocol):
    handler_id: DocumentViewerHandlerId
    binding_id: str
    binding_kind: str
    file_record: FileRecord
    title: str
    file_category: str
    onlyoffice_document_type: str | None
    namespace: str | None
    company_id: str
    user_id: str
    user_name: str
    editor_lang: str
    callback_public_base_url: str
    document_server_public_url: str
    jwt_secret: str
    download_token_ttl_seconds: int
    browser_public_base_url: str


class DocumentViewerHandler(Protocol):
    handler_id: DocumentViewerHandlerId

    def capabilities(self, *, file_record: FileRecord, integration_configured: bool) -> DocumentOpenCapabilities: ...

    async def build_open_config(self, ctx: ViewerOpenContext) -> DocumentOpenConfigResponse: ...
