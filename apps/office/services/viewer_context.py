"""Контекст открытия документа для viewer handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from core.documents.viewer.models import DocumentViewerHandlerId
from core.files.models import FileRecord

OfficeViewerLinkPermission = Literal["view", "edit"]


@dataclass(frozen=True)
class ViewerOpenContext:
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
    browser_document_server_url: str
    link_permission: OfficeViewerLinkPermission = "edit"
    public_link_token_hash: str | None = None
