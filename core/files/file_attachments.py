"""
Helpers для списков FileRef на границах сервисов (WorkItem, comments, resolution).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from pydantic import TypeAdapter

from core.files.file_ref import FileRef

_FILE_REFS_ADAPTER: TypeAdapter[list[FileRef]] = TypeAdapter(list[FileRef])


def parse_file_refs(raw: object) -> list[FileRef]:
    if raw is None:
        return []
    if isinstance(raw, list):
        if not raw:
            return []
        return _FILE_REFS_ADAPTER.validate_python(raw)
    raise TypeError(f"files must be list, got {type(raw).__name__}")


def merge_file_refs(*groups: Iterable[FileRef]) -> list[FileRef]:
    merged: list[FileRef] = []
    seen: set[str] = set()
    for group in groups:
        for file_ref in group:
            file_id = file_ref.file_id
            if file_id is None:
                continue
            if file_id in seen:
                continue
            seen.add(file_id)
            merged.append(file_ref)
    return merged


def file_ref_ids(files: Sequence[FileRef]) -> list[str]:
    ids: list[str] = []
    for file_ref in files:
        if file_ref.file_id is None:
            continue
        ids.append(file_ref.file_id)
    return ids


def minimal_file_refs_from_file_ids(file_ids: Sequence[str]) -> list[FileRef]:
    """Минимальный FileRef snapshot по списку file_id (метаданные подгружаются UI)."""
    refs: list[FileRef] = []
    for raw_id in file_ids:
        file_id = str(raw_id).strip()
        if not file_id:
            continue
        refs.append(
            FileRef(
                file_id=file_id,
                original_name=file_id,
                content_type="application/octet-stream",
                file_size=0,
            )
        )
    return refs
