"""
DocxTemplater — одна ссылка на файл (FileRef): dict из state.files, FileRecord или FileResponse.

- ``await fill(file_ref, context, *, strict=..., date_iso=...)`` → bytes;
- ``await fill_and_create(..., strict=..., date_iso=..., public=...)`` → FileMetadata.
"""

from __future__ import annotations

import base64
from typing import Any, Mapping, Optional

from core.files.docx_template.engine import render_docx_template_bytes
from core.files.docx_template.files_ref import read_template_bytes_from_file_ref
from core.files.file_ref import FileRef
from core.files.models import FileMetadata
from core.files.writer import FileWriteError, FileWriter


class DocxTemplater:
    """
    Заполнение .docx с плейсхолдерами Jinja2 (docxtpl).

    Источник шаблона — FileRef: локальный path, HTTP url или file_id в хранилище (как у FileReader).
    """

    async def fill(
        self,
        file_ref: FileRef,
        context: Mapping[str, Any],
        *,
        strict: bool = False,
        date_iso: bool = True,
    ) -> bytes:
        template_bytes = await read_template_bytes_from_file_ref(file_ref)
        return render_docx_template_bytes(
            template_bytes,
            context,
            strict=strict,
            date_iso=date_iso,
        )

    async def fill_and_create(
        self,
        *,
        file_ref: FileRef,
        context: Mapping[str, Any],
        output_original_name: str,
        strict: bool = False,
        date_iso: bool = True,
        public: bool = True,
        writer: Optional[FileWriter] = None,
    ) -> FileMetadata:
        name = (output_original_name or "").strip()
        if not name.lower().endswith(".docx"):
            raise FileWriteError(
                "output_original_name должен заканчиваться на .docx"
            )

        rendered = await self.fill(
            file_ref,
            context,
            strict=strict,
            date_iso=date_iso,
        )
        b64 = base64.b64encode(rendered).decode("ascii")
        fw = writer if writer is not None else FileWriter()
        return await fw.write(
            content=b64,
            original_name=name,
            content_mode="base64",
            public=public,
        )


__all__ = ["DocxTemplater"]
