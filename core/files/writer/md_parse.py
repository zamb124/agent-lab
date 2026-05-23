"""Разбор markdown на последовательность текст / таблица / изображение."""

from __future__ import annotations

import re
from typing import Any

from core.files.writer.exceptions import FileWriteError

_MD_IMG = re.compile(
    r"!\[([^\]]*)\]\(\s*<?([^>\s)]+)>?\s*(?:\s+[\"'][^\"']*[\"'])?\s*\)",
)


def split_text_and_tables(text: str) -> list[dict[str, Any]]:
    """Делит фрагмент markdown на блоки text и table (GFM-строки с |)."""
    lines = text.split("\n")
    out: list[dict[str, Any]] = []
    i = 0
    n = len(lines)
    while i < n:
        if lines[i].strip().startswith("|"):
            block: list[str] = []
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append({"kind": "table", "raw": "\n".join(block)})
        else:
            block = []
            while i < n and not lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            joined = "\n".join(block)
            if joined.strip():
                out.append({"kind": "text", "raw": joined})
    return out


def flatten_markdown_segments(md: str) -> list[dict[str, Any]]:
    """
    Порядок как в исходном markdown: чередование текста (с таблицами) и картинок ![]().
    """
    segments: list[dict[str, Any]] = []
    pos = 0
    for m in _MD_IMG.finditer(md):
        before = md[pos : m.start()]
        if before.strip():
            segments.extend(split_text_and_tables(before))
        url = m.group(2).strip().strip("<>")
        segments.append({"kind": "image", "url": url})
        pos = m.end()
    tail = md[pos:]
    if tail.strip():
        segments.extend(split_text_and_tables(tail))
    return segments


def parse_gfm_table(raw: str) -> list[list[str]]:
    """Парсит GFM-таблицу в матрицу ячеек; строку-разделитель |---| пропускает."""
    rows: list[list[str]] = []
    for line in raw.strip().split("\n"):
        line_st = line.strip()
        if not line_st.startswith("|"):
            continue
        inner = line_st.strip("|")
        cells = [c.strip() for c in inner.split("|")]
        if not cells:
            continue
        if all(_is_separator_cell(c) for c in cells):
            continue
        rows.append(cells)
    if not rows:
        raise FileWriteError("Не удалось разобрать markdown-таблицу (нет строк данных)")
    return rows


def _is_separator_cell(cell: str) -> bool:
    s = cell.strip()
    if not s:
        return False
    return bool(re.fullmatch(r":?-{3,}:?", s))
