"""Сегмент пути Документов: одно правило для каталога и имени файла."""

from __future__ import annotations

import unicodedata

_MAX_SEGMENT_BYTES = 255
_FORBIDDEN = frozenset("/\\\x00")


def title_key(segment: str) -> str:
    return unicodedata.normalize("NFC", segment).casefold()


def name_key(original_name: str) -> str:
    return title_key(original_name)


def validate_segment(segment: str) -> str:
    if segment != segment.strip() or segment.strip() == "":
        raise ValueError("path segment must be a non-empty trimmed name")
    if segment in {".", ".."}:
        raise ValueError("path segment must not be '.' or '..'")
    if any(char in _FORBIDDEN or ord(char) < 32 for char in segment):
        raise ValueError("path segment must not contain slash or control characters")
    if len(segment.encode("utf-8")) > _MAX_SEGMENT_BYTES:
        raise ValueError("path segment exceeds 255 UTF-8 bytes")
    return segment


def validate_original_name(original_name: str) -> str:
    return validate_segment(original_name)


def validate_relative_dir(relative_dir: str) -> list[str]:
    stripped = relative_dir.strip()
    if stripped == "":
        raise ValueError("relative_dir must be a non-empty POSIX path")
    if stripped.startswith("/") or stripped.endswith("/"):
        raise ValueError("relative_dir must not have a leading or trailing slash")
    segments = stripped.split("/")
    for segment in segments:
        if segment in {"", ".", ".."}:
            raise ValueError("relative_dir segments must not be empty, '.' or '..'")
        _ = validate_segment(segment)
    return segments


def split_catalog_path(catalog_path: list[str]) -> list[str]:
    if len(catalog_path) > 32:
        raise ValueError("catalog path depth exceeds 32")
    return [validate_segment(segment) for segment in catalog_path]


def autorename(original_name: str, taken: int) -> str:
    if taken < 1:
        raise ValueError("taken must be >= 1")
    dot = original_name.rfind(".")
    if dot > 0:
        return f"{original_name[:dot]} ({taken}){original_name[dot:]}"
    return f"{original_name} ({taken})"
