"""
Логика типов OnlyOffice: согласованность documentType и расширения файла.
"""

from __future__ import annotations

import pytest

from apps.office.services.document_type import (
    onlyoffice_document_type_for_upload,
    onlyoffice_file_type_for_binding,
    resolve_onlyoffice_document_type_for_editor,
)


def test_resolve_editor_prefers_extension_over_stored_word_for_xlsx():
    assert resolve_onlyoffice_document_type_for_editor("word", "report.xlsx") == "cell"


def test_resolve_editor_prefers_extension_over_stored_cell_for_docx():
    assert resolve_onlyoffice_document_type_for_editor("cell", "letter.docx") == "word"


def test_resolve_editor_falls_back_when_no_supported_extension():
    assert resolve_onlyoffice_document_type_for_editor("slide", "unknown.bin") == "slide"


def test_upload_by_filename_xlsx():
    dtype, ft = onlyoffice_document_type_for_upload("a.xlsx", "application/octet-stream")
    assert dtype == "cell"
    assert ft == "xlsx"


def test_upload_blob_filename_uses_spreadsheet_mime():
    dtype, ft = onlyoffice_document_type_for_upload(
        "blob",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert dtype == "cell"
    assert ft == "xlsx"


def test_upload_rejects_unknown_mime_without_extension():
    with pytest.raises(ValueError, match="Неподдерживаемый тип файла"):
        onlyoffice_document_type_for_upload("blob", "application/octet-stream")


def test_file_type_for_binding_aligns_with_resolved_editor_type():
    stored_wrong = "word"
    original = "data.xlsx"
    editor_t = resolve_onlyoffice_document_type_for_editor(stored_wrong, original)
    ft = onlyoffice_file_type_for_binding(editor_t, original)
    assert editor_t == "cell"
    assert ft == "xlsx"
