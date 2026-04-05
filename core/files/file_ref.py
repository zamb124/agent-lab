"""
Единая ссылка на файл для core.files: запись из state.files, FileRecord / FileResponse из БД или API.

Все сервисы могут передавать либо dict (name, path и/или file_id, url), либо модель записи.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, TypeAlias, Union

from core.files.models import FileRecord, FileResponse

DOWNLOAD_FILE_ID_RE = re.compile(r"/files/download/([^/?#]+)")


def file_id_from_download_url(url: str) -> str | None:
    m = DOWNLOAD_FILE_ID_RE.search(url.strip())
    return m.group(1) if m else None


FileRef: TypeAlias = Union[FileRecord, FileResponse, Mapping[str, Any]]


def normalize_file_ref(ref: FileRef) -> dict[str, Any]:
    if isinstance(ref, FileRecord):
        return {
            "file_id": ref.file_id,
            "name": ref.original_name,
            "original_name": ref.original_name,
            "mime_type": ref.content_type,
            "url": ref.url,
        }
    if isinstance(ref, FileResponse):
        return {
            "file_id": ref.file_id,
            "name": ref.original_name,
            "original_name": ref.original_name,
            "mime_type": ref.content_type,
            "url": ref.url,
        }
    if not isinstance(ref, Mapping):
        raise TypeError(
            f"Ожидался FileRecord, FileResponse или mapping, получено: {type(ref).__name__}"
        )
    out = dict(ref)
    name_v = out.get("name")
    original_v = out.get("original_name")
    if (not name_v or not str(name_v).strip()) and original_v and str(original_v).strip():
        out["name"] = str(original_v).strip()
    return out


__all__ = [
    "DOWNLOAD_FILE_ID_RE",
    "FileRef",
    "file_id_from_download_url",
    "normalize_file_ref",
]
