"""
Текстовое превью файла из хранилища (тот же пайплайн, что FileReader, без vision для изображений).
"""

from __future__ import annotations

from core.files.models import FileReadPreviewResponse
from core.files.reader.models import FileReadKind
from core.files.reader.service import FileReader, read_stored_file_by_id

_PREVIEW_MAX_CHARS = 12_000

_IMAGE_PREVIEW_NOTE = (
    "Изображение: при прикреплении текст не извлекается. "
    "Во время выполнения ноды используйте reader.read или vision."
)


async def build_stored_file_text_preview(*, file_id: str, original_name: str) -> FileReadPreviewResponse:
    raw, resolved_name = await read_stored_file_by_id(file_id)
    name = (original_name or "").strip() or resolved_name

    reader = FileReader()
    info = reader.recognize_file_type(file_name=name, head=raw[:8192])

    if info.detected_kind == FileReadKind.IMAGE:
        return FileReadPreviewResponse(
            text="",
            truncated=False,
            page_count=0,
            detected_kind=info.detected_kind.value,
            content_type=info.content_type,
            warnings=[],
            preview_note=_IMAGE_PREVIEW_NOTE,
        )

    result = await reader.read(raw, file_name=name)

    parts: list[str] = []
    for page in result.pages:
        chunk = (page.text or "").strip()
        if chunk:
            parts.append(chunk)

    if len(parts) > 1:
        full = "\n\n---\n\n".join(parts)
    elif len(parts) == 1:
        full = parts[0]
    else:
        full = ""

    truncated = len(full) > _PREVIEW_MAX_CHARS
    text = full[:_PREVIEW_MAX_CHARS] if truncated else full

    return FileReadPreviewResponse(
        text=text,
        truncated=truncated,
        page_count=result.page_count,
        detected_kind=result.detected_kind.value,
        content_type=result.content_type,
        warnings=list(result.warnings),
        preview_note=None,
    )
