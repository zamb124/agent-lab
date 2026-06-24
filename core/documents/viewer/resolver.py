"""Резолв категории файла и viewer handler id."""

from __future__ import annotations

from pathlib import Path

from core.documents.viewer.models import DocumentViewerHandlerId
from core.files.types import FileCategory, ext_to_category, mime_to_category

UNKNOWN_FILE_CATEGORY = "unknown"


def resolve_file_category_for_upload(filename: str, content_type: str | None) -> str:
    """Категория файла для binding; unknown если расширение и MIME не в реестре."""
    ext = Path(filename).suffix.lower()
    if ext:
        category = ext_to_category(ext)
        if category is not None:
            return category.value
    if content_type:
        normalized = content_type.split(";", 1)[0].strip().lower()
        category = mime_to_category(normalized)
        if category is not None:
            return category.value
    return UNKNOWN_FILE_CATEGORY


def file_category_to_enum(file_category: str) -> FileCategory | None:
    try:
        return FileCategory(file_category)
    except ValueError:
        return None


def resolve_viewer_handler_id(
    *,
    file_category: str,
    onlyoffice_eligible: bool,
    integration_configured: bool,
) -> DocumentViewerHandlerId:
    if onlyoffice_eligible:
        if not integration_configured:
            raise ValueError("office_integration_not_configured")
        return "onlyoffice"
    category = file_category_to_enum(file_category)
    if category == FileCategory.IMAGE:
        return "image"
    if category in {FileCategory.AUDIO, FileCategory.VIDEO}:
        return "media"
    if category == FileCategory.TEXT:
        return "text"
    return "binary"
