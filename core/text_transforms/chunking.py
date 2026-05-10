"""Разбиение длинного текста на чанки по границам абзацев/строк."""

from __future__ import annotations


def split_text_into_markdown_chunks(text: str, max_chunk_chars: int) -> list[str]:
    if max_chunk_chars <= 0:
        raise ValueError("max_chunk_chars должен быть положительным")
    t = text.strip()
    if not t:
        return []
    if len(t) <= max_chunk_chars:
        return [t]

    parts: list[str] = []
    start = 0
    n = len(t)
    while start < n:
        end = min(start + max_chunk_chars, n)
        if end < n:
            window = t[start:end]
            cut_pp = window.rfind("\n\n")
            if cut_pp != -1 and cut_pp >= max_chunk_chars // 4:
                end = start + cut_pp
            else:
                cut_nl = window.rfind("\n")
                if cut_nl != -1 and cut_nl >= max_chunk_chars // 4:
                    end = start + cut_nl + 1
        chunk = t[start:end].strip()
        if chunk:
            parts.append(chunk)
        start = end
    return parts
