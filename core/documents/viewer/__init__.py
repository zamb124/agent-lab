"""Viewer handler contracts для открытия файлов (OnlyOffice — один из handlers)."""

from core.documents.viewer.models import (
    BinaryOpenPayload,
    DocumentOpenCapabilities,
    DocumentOpenConfigResponse,
    DocumentViewerHandlerId,
    ImageOpenPayload,
    MediaOpenPayload,
    MediaViewerKind,
    OnlyOfficeOpenPayload,
    TextOpenPayload,
)
from core.documents.viewer.resolver import (
    resolve_file_category_for_upload,
    resolve_viewer_handler_id,
)

__all__ = [
    "BinaryOpenPayload",
    "DocumentOpenCapabilities",
    "DocumentOpenConfigResponse",
    "DocumentViewerHandlerId",
    "ImageOpenPayload",
    "MediaOpenPayload",
    "MediaViewerKind",
    "OnlyOfficeOpenPayload",
    "TextOpenPayload",
    "resolve_file_category_for_upload",
    "resolve_viewer_handler_id",
]
