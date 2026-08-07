"""Runtime-хелперы для flow tools."""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence

from core.files.file_ref import FileRef


def normalize_file_lookup_name(value: str | None) -> str:
    """Нормализует имя файла для устойчивого поиска в state.files."""
    if value is None:
        return ""
    text = value.strip().strip("`'\"")
    return unicodedata.normalize("NFC", text).casefold()


def normalize_file_lookup_key(value: str | None) -> str:
    normalized = normalize_file_lookup_name(value)
    decomposed = unicodedata.normalize("NFKD", normalized)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def find_file(files: Sequence[FileRef], name: str | None = None) -> FileRef | None:
    """Ищет файл в state.files по original_name; без name возвращает последний файл."""
    if not files:
        return None
    if not name:
        return files[-1]
    for file_ref in files:
        if file_ref.original_name == name:
            return file_ref
    normalized_name = normalize_file_lookup_name(name)
    for file_ref in files:
        if normalize_file_lookup_name(file_ref.original_name) == normalized_name:
            return file_ref
    name_key = normalize_file_lookup_key(name)
    for file_ref in files:
        if normalize_file_lookup_key(file_ref.original_name) == name_key:
            return file_ref
    for file_ref in files:
        file_key = normalize_file_lookup_key(file_ref.original_name)
        if name_key and name_key in file_key:
            return file_ref
    return None
