"""
Байты шаблона .docx из FileRef (state.files, FileRecord, FileResponse).
"""

from __future__ import annotations

from core.files.docx_template.exceptions import DocxTemplateSourceError
from core.files.file_ref import FileRef, normalize_file_ref
from core.files.reader.models import ReadOptions, merge_file_ref_read_options
from core.files.reader.service import FileReader


async def read_template_bytes_from_file_ref(ref: FileRef) -> bytes:
    finfo = normalize_file_ref(ref)
    declared = (finfo.get("name") or finfo.get("original_name") or "").strip()
    if not declared.lower().endswith(".docx"):
        raise DocxTemplateSourceError(
            f"Шаблон должен быть файлом .docx, получено имя: {declared!r}"
        )

    reader = FileReader()
    opts = merge_file_ref_read_options(finfo, ReadOptions())
    raw, resolved_name = await reader._raw_from_file_ref(finfo, opts)
    if not resolved_name.lower().endswith(".docx"):
        raise DocxTemplateSourceError(
            f"Шаблон должен быть файлом .docx, после разрешения источника: {resolved_name!r}"
        )
    return raw


__all__ = ["read_template_bytes_from_file_ref"]
