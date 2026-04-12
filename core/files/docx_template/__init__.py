"""
Шаблонизация DOCX (docxtpl / Jinja2 внутри Word).

Источник шаблона — **FileRef**: элемент ``state.files`` (dict), ``FileRecord`` / ``FileResponse``.

- ``await DocxTemplater().fill(file_ref, context, *, strict=False, date_iso=True)`` → bytes;
- ``await fill_and_create(file_ref=..., context=..., output_original_name=..., strict=..., date_iso=..., public=...)`` → ``FileMetadata``.

Сырые байты без файла на диске: ``render_docx_template_bytes(..., strict=..., date_iso=...)``.
"""

from core.files.docx_template.engine import render_docx_template_bytes
from core.files.docx_template.exceptions import (
    DocxTemplateContextError,
    DocxTemplateError,
    DocxTemplateInvalidError,
    DocxTemplateSourceError,
    DocxTemplateSyntaxError,
)
from core.files.docx_template.files_ref import read_template_bytes_from_file_ref
from core.files.docx_template.service import DocxTemplater

__all__ = [
    "DocxTemplater",
    "DocxTemplateContextError",
    "DocxTemplateError",
    "DocxTemplateInvalidError",
    "DocxTemplateSourceError",
    "DocxTemplateSyntaxError",
    "read_template_bytes_from_file_ref",
    "render_docx_template_bytes",
]
