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


def supports_onlyoffice_viewer(filename: str, content_type: str | None) -> bool:
    try:
        _ = onlyoffice_document_type_for_upload(filename, content_type)
        return True
    except ValueError:
        return False


def onlyoffice_document_type_and_file_type(filename: str) -> tuple[str, str]:
    """
    Возвращает:
        (documentType, fileType) — например ("word", "docx").
    """
    ext = Path(filename).suffix.lower().lstrip(".")
    if not ext:
        raise ValueError("У файла нет расширения")
    if ext in _ONLYOFFICE_WORD_EXTS:
        return "word", ext
    if ext in _ONLYOFFICE_CELL_EXTS:
        return "cell", ext
    if ext in _ONLYOFFICE_SLIDE_EXTS:
        return "slide", ext
    raise ValueError(
        f"Неподдерживаемое расширение для OnlyOffice: .{ext} "
        + "(ожидаются doc/docx/pdf/xls/xlsx/ppt/pptx и odt/ods/odp/rtf/txt/csv)"
    )


def onlyoffice_document_type_for_upload(filename: str, content_type: str | None) -> tuple[str, str]:
    """
    Тип привязки для POST /documents: сначала по имени файла, иначе по MIME (браузеры часто шлют «blob» без расширения).
    """
    raw = (filename or "").strip() or "document"
    try:
        return onlyoffice_document_type_and_file_type(raw)
    except ValueError:
        pass
    ct = (content_type or "").split(";")[0].strip().lower()
    mapped = _MIME_TO_DTYPE_AND_EXT.get(ct)
    if mapped is not None:
        return mapped
    raise ValueError(
        f"Неподдерживаемый тип файла: не удалось определить по имени «{raw}» "
        + f"и MIME «{ct or 'нет'}»"
    )


def resolve_onlyoffice_document_type_for_editor(
    stored_document_type: str,
    original_name: str,
) -> str:
    """
    Тип редактора в JWT для OnlyOffice: должен совпадать с document.fileType.
    Иначе DS открывает неверный модуль (например Word для .xlsx), если в БД устарел document_type.
    """
    try:
        dtype, _ = onlyoffice_document_type_and_file_type(original_name)
        return dtype
    except ValueError:
        return stored_document_type


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
