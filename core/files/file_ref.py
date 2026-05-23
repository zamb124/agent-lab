"""
Единая ссылка на файл для core.files: запись из state.files, FileRecord / FileResponse из БД или API.

Все сервисы передают канонический dict state.files (`original_name`, `url` и/или `file_id`)
либо модель записи.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, TypeAlias

from core.files.models import FileRecord, FileResponse

DOWNLOAD_FILE_ID_RE = re.compile(r"/files/download/([^/?#]+)")


def file_id_from_download_url(url: str) -> str | None:
    m = DOWNLOAD_FILE_ID_RE.search(url.strip())
    return m.group(1) if m else None


FileRef: TypeAlias = FileRecord | FileResponse | Mapping[str, Any]


def normalize_file_ref(ref: FileRef) -> dict[str, Any]:
    if isinstance(ref, FileRecord):
        return {
            "file_id": ref.file_id,
            "original_name": ref.original_name,
            "content_type": ref.content_type,
            "file_size": ref.file_size,
            "url": ref.url,
        }
    if isinstance(ref, FileResponse):
        return {
            "file_id": ref.file_id,
            "original_name": ref.original_name,
            "content_type": ref.content_type,
            "file_size": ref.file_size,
            "url": ref.url,
        }
    if not isinstance(ref, Mapping):
        raise TypeError(
            f"Ожидался FileRecord, FileResponse или mapping, получено: {type(ref).__name__}"
        )
    out = dict(ref)
    legacy_keys = {"name", "path", "mime_type", "size", "type"} & set(out)
    if legacy_keys:
        keys = ", ".join(sorted(legacy_keys))
        raise ValueError(f"FileRef содержит legacy-поля: {keys}")
    original_name = out.get("original_name")
    if not isinstance(original_name, str) or not original_name.strip():
        raise ValueError("FileRef.original_name обязателен")
    file_id = out.get("file_id")
    url = out.get("url")
    has_file_id = isinstance(file_id, str) and file_id.strip()
    has_url = isinstance(url, str) and url.strip()
    if not has_file_id and not has_url:
        raise ValueError("FileRef должен содержать file_id или url")
    return out


__all__ = [
    "DOWNLOAD_FILE_ID_RE",
    "FileRef",
    "file_id_from_download_url",
    "normalize_file_ref",
]
