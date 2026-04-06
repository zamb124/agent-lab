"""
Нарезка текста для импорта базы знаний в CRM.

Лимиты и форматы — см. `.cursor/rules/crm.mdc` (раздел knowledge import).
"""

from __future__ import annotations

import re

MAX_IMPORT_TEXT_CHARS = 10_000_000
DEFAULT_CHUNK_MAX_CHARS = 50_000
MIN_CHUNK_MAX_CHARS = 2_000
MAX_CHUNK_MAX_CHARS = 500_000


def validate_chunk_max_chars(value: int) -> int:
    if value < MIN_CHUNK_MAX_CHARS or value > MAX_CHUNK_MAX_CHARS:
        raise ValueError(
            f"chunk_max_chars должен быть в [{MIN_CHUNK_MAX_CHARS}, {MAX_CHUNK_MAX_CHARS}], получено {value}"
        )
    return value


def split_knowledge_text(
    text: str,
    *,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    split_by_headings: bool = False,
) -> list[str]:
    if not isinstance(text, str):
        raise TypeError("text должен быть str")
    if len(text) > MAX_IMPORT_TEXT_CHARS:
        raise ValueError(
            f"Текст импорта превышает лимит {MAX_IMPORT_TEXT_CHARS} символов: {len(text)}"
        )
    chunk_max_chars = validate_chunk_max_chars(chunk_max_chars)

    if text.strip() == "":
        raise ValueError("Текст импорта пуст")

    if split_by_headings:
        parts = _split_by_markdown_headings(text)
    else:
        parts = [text.strip()]

    return _enforce_max_chunk_size(parts, chunk_max_chars)


def _split_by_markdown_headings(text: str) -> list[str]:
    raw = text.replace("\r\n", "\n")
    lines = raw.split("\n")
    chunks: list[str] = []
    current: list[str] = []

    heading_re = re.compile(r"^#{1,6}\s+\S")

    for line in lines:
        stripped = line.strip()
        if heading_re.match(stripped) and current:
            piece = "\n".join(current).strip()
            if piece:
                chunks.append(piece)
            current = [line]
        else:
            current.append(line)

    if current:
        piece = "\n".join(current).strip()
        if piece:
            chunks.append(piece)

    if not chunks:
        return [raw.strip()]
    return chunks


def _enforce_max_chunk_size(parts: list[str], max_chars: int) -> list[str]:
    out: list[str] = []
    for part in parts:
        if len(part) <= max_chars:
            out.append(part)
            continue
        for i in range(0, len(part), max_chars):
            chunk = part[i : i + max_chars].strip()
            if chunk:
                out.append(chunk)
    return out
