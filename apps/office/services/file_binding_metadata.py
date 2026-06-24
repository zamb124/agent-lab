"""Метаданные binding: file_category и onlyoffice_document_type."""

from __future__ import annotations

from pathlib import Path

from apps.office.services.document_type import (
    onlyoffice_document_type_for_upload,
    supports_onlyoffice_viewer,
)
from core.documents.viewer.resolver import resolve_file_category_for_upload
from core.files.types import FileCategory


def resolve_binding_metadata(
    filename: str,
    content_type: str | None,
) -> tuple[str, str | None]:
    """
    Возвращает (file_category, onlyoffice_document_type).

    onlyoffice_document_type заполняется только если файл открывается через OnlyOffice.
    """
    file_category = resolve_file_category_for_upload(filename, content_type)
    onlyoffice_document_type: str | None = None
    normalized_ct = content_type.split(";", 1)[0].strip() if content_type else None
    try:
        category_enum = FileCategory(file_category)
    except ValueError:
        return file_category, None
    if category_enum in {
        FileCategory.OFFICE_DOC,
        FileCategory.SPREADSHEET,
        FileCategory.PRESENTATION,
        FileCategory.PDF,
        FileCategory.TEXT,
    } and supports_onlyoffice_viewer(filename, normalized_ct):
        onlyoffice_document_type, _ = onlyoffice_document_type_for_upload(filename, normalized_ct)
        if onlyoffice_document_type == "word":
            file_category = FileCategory.OFFICE_DOC.value
        elif onlyoffice_document_type == "cell":
            file_category = FileCategory.SPREADSHEET.value
        elif onlyoffice_document_type == "slide":
            file_category = FileCategory.PRESENTATION.value
    return file_category, onlyoffice_document_type


def onlyoffice_document_type_for_binding_row(
    *,
    onlyoffice_document_type: str | None,
    original_name: str,
) -> str:
    """Тип OnlyOffice для JWT; при отсутствии в binding — из имени файла."""
    if onlyoffice_document_type:
        return onlyoffice_document_type
    normalized_ct = "application/octet-stream"
    ext = Path(original_name).suffix.lower()
    if ext == ".pdf":
        normalized_ct = "application/pdf"
    try:
        dtype, _ = onlyoffice_document_type_for_upload(original_name, normalized_ct)
        return dtype
    except ValueError as exc:
        raise ValueError(f"OnlyOffice тип не определён для {original_name}") from exc


def migration_document_type_to_file_category(document_type: str) -> tuple[str, str | None]:
    """Маппинг значений document_type из Alembic backfill (word/cell/slide)."""
    if document_type == "word":
        return FileCategory.OFFICE_DOC.value, "word"
    if document_type == "cell":
        return FileCategory.SPREADSHEET.value, "cell"
    if document_type == "slide":
        return FileCategory.PRESENTATION.value, "slide"
    return document_type, None
