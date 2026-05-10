"""Снятие одиночной внешней GFM-ограды ```markdown/``` с текста (ответы LLM)."""

from __future__ import annotations

import re


def strip_outer_markdown_code_fence(raw: str) -> str:
    trimmed = raw.strip()
    if not trimmed:
        return ""
    open_m = re.match(r"^```(?:markdown|md)?\s*\r?\n", trimmed, re.IGNORECASE)
    if not open_m:
        return trimmed
    after_open = trimmed[open_m.end() :]
    close_idx = after_open.rfind("```")
    if close_idx < 0:
        return trimmed
    inner = after_open[:close_idx].strip()
    return inner if inner else trimmed
