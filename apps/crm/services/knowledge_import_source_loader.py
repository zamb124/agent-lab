"""
Извлечение полного текста из файла в shared storage (тот же пайплайн, что превью).
"""

from __future__ import annotations

from core.files.reader.service import FileReader, _read_stored_file_by_id


async def load_text_from_stored_file_id(file_id: str) -> str:
    fid = str(file_id).strip()
    if not fid:
        raise ValueError("file_id пуст")
    raw, name = await _read_stored_file_by_id(fid)
    reader = FileReader()
    result = await reader.read(raw, file_name=name)
    parts: list[str] = []
    for page in result.pages:
        chunk = (page.text or "").strip()
        if chunk:
            parts.append(chunk)
    if len(parts) > 1:
        return "\n\n---\n\n".join(parts)
    if len(parts) == 1:
        return parts[0]
    return ""
