"""
Байты шаблона .docx из FileRef (state.files, FileRecord, FileResponse).
"""

from __future__ import annotations

from core.files.docx_template.exceptions import DocxTemplateSourceError
from core.files.file_ref import FileRef
from core.files.reader.models import ReadOptions, merge_file_ref_read_options
from core.files.reader.service import FileReader


async def read_template_bytes_from_file_ref(ref: FileRef) -> bytes:
    if not ref.original_name.lower().endswith(".docx"):
        raise DocxTemplateSourceError(
            f"Шаблон должен быть файлом .docx, получено имя: {ref.original_name!r}"
        )

    reader = FileReader()
    opts = merge_file_ref_read_options(ref, ReadOptions())
    raw, resolved_name = await reader.raw_from_file_ref(ref, opts)
    if not resolved_name.lower().endswith(".docx"):
        raise DocxTemplateSourceError(
            f"Шаблон должен быть файлом .docx, после разрешения источника: {resolved_name!r}"
        )
    return raw


__all__ = ["read_template_bytes_from_file_ref"]
