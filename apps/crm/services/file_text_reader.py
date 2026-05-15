"""
Извлечение полного текста из файла в shared storage (тот же пайплайн, что превью).
"""

from __future__ import annotations

from core.files.reader.service import FileReader, _read_stored_file_by_id
from core.files.reader.models import ReadPage


def _join_pages(pages: list[ReadPage]) -> str:
    parts: list[str] = []
    for page in pages:
        chunk = (page.text or "").strip()
        if chunk:
            parts.append(chunk)
    if len(parts) > 1:
        return "\n\n---\n\n".join(parts)
    if len(parts) == 1:
        return parts[0]
    return ""


async def load_text_from_stored_file_id(file_id: str) -> str:
    """Извлечь полный текст файла из shared storage по file_id."""
    fid = str(file_id).strip()
    if not fid:
        raise ValueError("file_id пуст")
    raw, name = await _read_stored_file_by_id(fid)
    reader = FileReader()
    result = await reader.read(raw, file_name=name)
    return _join_pages(result.pages)


async def load_text_and_name_from_stored_file_id(file_id: str) -> tuple[str, str]:
    """Извлечь текст и оригинальное имя файла из shared storage по file_id."""
    fid = str(file_id).strip()
    if not fid:
        raise ValueError("file_id пуст")
    raw, name = await _read_stored_file_by_id(fid)
    reader = FileReader()
    result = await reader.read(raw, file_name=name)
    return _join_pages(result.pages), name


async def load_text_from_bytes(raw: bytes, file_name: str) -> str:
    """Извлечь текст из байтов файла (без чтения из storage)."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ValueError("raw must be bytes")
    data = bytes(raw)
    if len(data) == 0:
        raise ValueError("raw file bytes empty")
    nm = str(file_name).strip() if file_name else "file"
    reader = FileReader()
    result = await reader.read(data, file_name=nm)
    return _join_pages(result.pages)
