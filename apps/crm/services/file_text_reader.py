"""
Извлечение полного текста из файла в shared storage (канонический FileReader.read).
"""

from __future__ import annotations

from core.files.reader.models import ReadFileArgs, UniversalPage
from core.files.reader.service import FileReader, read_stored_file_by_id


def _join_pages(pages: list[UniversalPage]) -> str:
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
    raw, name = await read_stored_file_by_id(fid)
    reader = FileReader()
    extract = await reader.read(raw, ReadFileArgs(page_end=-1), file_name=name, file_id=fid)
    return _join_pages(extract.pages)


async def load_text_and_name_from_stored_file_id(file_id: str) -> tuple[str, str]:
    """Извлечь текст и оригинальное имя файла из shared storage по file_id."""
    fid = str(file_id).strip()
    if not fid:
        raise ValueError("file_id пуст")
    raw, name = await read_stored_file_by_id(fid)
    reader = FileReader()
    extract = await reader.read(raw, ReadFileArgs(page_end=-1), file_name=name, file_id=fid)
    return _join_pages(extract.pages), name


async def load_text_from_bytes(raw: bytes, file_name: str) -> str:
    """Извлечь текст из байтов файла (без чтения из storage)."""
    data = bytes(raw)
    if len(data) == 0:
        raise ValueError("raw file bytes empty")
    nm = str(file_name).strip() if file_name else "file"
    reader = FileReader()
    extract = await reader.read(data, ReadFileArgs(page_end=-1), file_name=nm)
    return _join_pages(extract.pages)
