"""Структурные (без LLM) суммаризаторы: CSV/TSV/spreadsheet, JSON/XML/YAML, код."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import cast

from core.files.reader.models import UniversalPage
from core.types import JsonValue, require_json_value

_MAX_STRUCT_ROWS: int = 5
_MAX_KEYS: int = 40
_MAX_OUTLINE_LINES: int = 40


def _detect_delimiter(line: str) -> str:
    if "\t" in line:
        return "\t"
    if ";" in line and line.count(";") >= line.count(","):
        return ";"
    return ","


def summarize_tabular(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    delimiter = _detect_delimiter(lines[0])
    header = lines[0].split(delimiter)
    columns = ",".join(col.strip() for col in header)
    total_rows = max(len(lines) - 1, 0)
    preview = "\n".join(lines[1 : 1 + _MAX_STRUCT_ROWS])
    head = f"columns: {columns} (rows={total_rows})"
    return f"{head}\n{preview}" if preview else head


def _summarize_json_value(value: JsonValue, depth: int = 0) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    if isinstance(value, dict):
        for idx, (key, child) in enumerate(value.items()):
            if idx >= _MAX_KEYS:
                lines.append(f"{indent}...")
                break
            lines.append(f"{indent}{key}: {type(child).__name__}")
            if isinstance(child, (dict, list)) and depth < 2:
                lines.extend(_summarize_json_value(child, depth + 1))
    elif isinstance(value, list):
        lines.append(f"{indent}[list len={len(value)}]")
        if value and depth < 2:
            lines.extend(_summarize_json_value(value[0], depth + 1))
    else:
        lines.append(f"{indent}{type(value).__name__}")
    return lines


def summarize_json(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""
    try:
        parsed: JsonValue = require_json_value(
            cast(object, json.loads(stripped)), "summarize_json"
        )
    except (ValueError, TypeError):
        return summarize_outline(text)
    lines = _summarize_json_value(parsed)
    return "\n".join(lines[:_MAX_OUTLINE_LINES])


def summarize_outline(text: str) -> str:
    prefixes = (
        "def ",
        "class ",
        "async def ",
        "function ",
        "func ",
        "import ",
        "from ",
        "public ",
        "private ",
        "export ",
        "type ",
        "interface ",
        "struct ",
    )
    outline: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(prefixes):
            outline.append(line)
        if len(outline) >= _MAX_OUTLINE_LINES:
            break
    if not outline:
        return text[:400]
    return "\n".join(outline)


async def summarize_tabular_pages(
    pages: Sequence[UniversalPage], *, prompt: str, model: str
) -> list[str]:
    _ = (prompt, model)
    return [summarize_tabular(page.text) for page in pages]


async def summarize_json_pages(
    pages: Sequence[UniversalPage], *, prompt: str, model: str
) -> list[str]:
    _ = (prompt, model)
    return [summarize_json(page.text) for page in pages]


async def summarize_outline_pages(
    pages: Sequence[UniversalPage], *, prompt: str, model: str
) -> list[str]:
    _ = (prompt, model)
    return [summarize_outline(page.text) for page in pages]
