"""
Соответствие расширения файла типу редактора OnlyOffice (documentType / fileType).

Расширения здесь — подмножество единого реестра core.files.types.
"""

from pathlib import Path

from core.files.types import (
    FileCategory,
    accept_string_for,
    extensions_for,
)

ONLYOFFICE_CATEGORIES = (
    FileCategory.OFFICE_DOC,
    FileCategory.SPREADSHEET,
    FileCategory.PRESENTATION,
    FileCategory.PDF,
    FileCategory.TEXT,
)

ONLYOFFICE_ACCEPT_STRING = accept_string_for(*ONLYOFFICE_CATEGORIES)

_ONLYOFFICE_WORD_EXTS = {
    e.lstrip(".") for e in extensions_for(FileCategory.OFFICE_DOC, FileCategory.PDF)
} | {"txt"}
_ONLYOFFICE_CELL_EXTS = {
    e.lstrip(".") for e in extensions_for(FileCategory.SPREADSHEET)
} | {"csv"}
_ONLYOFFICE_SLIDE_EXTS = {
    e.lstrip(".") for e in extensions_for(FileCategory.PRESENTATION)
}

_MIME_TO_DTYPE_AND_EXT: dict[str, tuple[str, str]] = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ("cell", "xlsx"),
    "application/vnd.ms-excel": ("cell", "xls"),
    "text/csv": ("cell", "csv"),
    "text/comma-separated-values": ("cell", "csv"),
    "application/csv": ("cell", "csv"),
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": (
        "slide",
        "pptx",
    ),
    "application/vnd.ms-powerpoint": ("slide", "ppt"),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("word", "docx"),
    "application/msword": ("word", "doc"),
    "application/pdf": ("word", "pdf"),
}


def _onlyoffice_type_from_filename(filename: str) -> tuple[str, str] | None:
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext in _ONLYOFFICE_WORD_EXTS:
        return "word", ext
    if ext in _ONLYOFFICE_CELL_EXTS:
        return "cell", ext
    if ext in _ONLYOFFICE_SLIDE_EXTS:
        return "slide", ext
    return None


def _mime_onlyoffice_type(content_type: str | None) -> tuple[str, str] | None:
    header = "" if content_type is None else content_type
    ct = header.split(";")[0].strip().lower()
    return _MIME_TO_DTYPE_AND_EXT.get(ct)


def _upload_filename(filename: str) -> str:
    stripped = filename.strip()
    if stripped == "":
        return "document"
    return stripped


def supports_onlyoffice_viewer(filename: str, content_type: str | None) -> bool:
    raw = _upload_filename(filename)
    if _onlyoffice_type_from_filename(raw) is not None:
        return True
    return _mime_onlyoffice_type(content_type) is not None


def onlyoffice_document_type_and_file_type(filename: str) -> tuple[str, str]:
    """
    Возвращает:
        (documentType, fileType) — например ("word", "docx").
    """
    mapped = _onlyoffice_type_from_filename(filename)
    if mapped is not None:
        return mapped
    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext:
        raise ValueError("File has no extension")
    raise ValueError(
        f"Unsupported extension for OnlyOffice: .{ext} "
        + "(expected doc/docx/pdf/xls/xlsx/ppt/pptx and odt/ods/odp/rtf/txt/csv)"
    )


def onlyoffice_document_type_for_upload(filename: str, content_type: str | None) -> tuple[str, str]:
    """
    Тип привязки для POST /documents: сначала по имени файла, иначе по MIME (браузеры часто шлют «blob» без расширения).
    """
    raw = _upload_filename(filename)
    from_name = _onlyoffice_type_from_filename(raw)
    if from_name is not None:
        return from_name
    from_mime = _mime_onlyoffice_type(content_type)
    if from_mime is not None:
        return from_mime
    header = "" if content_type is None else content_type
    ct = header.split(";")[0].strip().lower()
    mime_label = ct if ct != "" else "none"
    raise ValueError(
        f"Unsupported file type: could not determine from name «{raw}» "
        + f"and MIME «{mime_label}»"
    )


def resolve_onlyoffice_document_type_for_editor(
    stored_document_type: str,
    original_name: str,
) -> str:
    """
    Тип редактора в JWT для OnlyOffice: должен совпадать с document.fileType.
    Иначе DS открывает неверный модуль (например Word для .xlsx), если в БД устарел document_type.
    """
    mapped = _onlyoffice_type_from_filename(original_name)
    if mapped is None:
        return stored_document_type
    document_type, _file_type = mapped
    return document_type


def onlyoffice_file_type_for_binding(document_type: str, original_name: str) -> str:
    ext = Path(original_name).suffix.lower().lstrip(".")
    if ext:
        return ext
    if document_type == "word":
        return "docx"
    if document_type == "cell":
        return "xlsx"
    if document_type == "slide":
        return "pptx"
    return "docx"
