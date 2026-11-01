#!/usr/bin/env python3
"""Баланс скобок в css`` template literals.

Незакрытый `(`/`{` внутри css`` не роняет сборку и не виден в typecheck, но при
adoptStyleSheets браузер молча проглатывает остаток stylesheet — вся визуальная
часть после битой строки перестаёт применяться (реальный инцидент:
`scale(calc(...;` убил все `.field-pill-*` правила). Гейт ловит этот класс:
`;`, `{`, `}` на ненулевой глубине `(`, stray `}`, незакрытые `(`/`{`/комментарий
к концу шаблона. Строки, `/* */` и `${}`-выражения при подсчёте пропускаются.
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as ROOT
from scripts.gates.kit import report

SCAN_DIRS = (
    ROOT / "core/frontend",
    ROOT / "apps",
    ROOT / "tests",
)

SKIP_DIR_NAMES = {
    "vendor",
    "node_modules",
    "ui-dist",
    "embed-dist",
    "__pycache__",
    ".venv",
    "dist",
}

IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_$.")


def _string_end(src: str, i: int) -> int:
    """i — позиция кавычки. Возвращает индекс за закрывающей кавычкой."""
    quote = src[i]
    i += 1
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == quote:
            return i + 1
        i += 1
    return n


def _expr_end(src: str, i: int) -> int:
    """i — позиция сразу после `${`. Возвращает индекс за закрывающей `}`.
    Внутри выражения пропускаются строки, комментарии и вложенные шаблоны."""
    n = len(src)
    depth = 0
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c in "'\"":
            i = _string_end(src, i)
            continue
        if c == "`":
            j = _template_end(src, i + 1)
            i = n if j < 0 else j + 1
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            if depth == 0:
                return i + 1
            depth -= 1
        i += 1
    return n


def _template_end(src: str, i: int) -> int:
    """i — позиция сразу после открывающего backtick. Возвращает позицию
    закрывающего backtick или -1."""
    n = len(src)
    while i < n:
        c = src[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return i
        if src.startswith("${", i):
            i = _expr_end(src, i + 2)
            continue
        i += 1
    return -1


def _iter_expr_spans(src: str, start: int, end: int) -> list[tuple[int, int]]:
    """Диапазоны `${...}` внутри тела шаблона (без учёта вложенных — они
    перекрываются внешним диапазоном, чего достаточно для рекурсивного обхода)."""
    spans: list[tuple[int, int]] = []
    i = start
    while i < end:
        if src[i] == "\\":
            i += 2
            continue
        if src.startswith("${", i):
            body = i + 2
            close = _expr_end(src, body)
            spans.append((body, min(close, end)))
            i = close
            continue
        i += 1
    return spans


def _scan_css(src: str, start: int, end: int, path: str, errors: list[str]) -> None:
    """Сканирует тело css`` шаблона [start, end)."""
    line = src.count("\n", 0, start) + 1
    paren = 0
    brace = 0
    i = start
    while i < end:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2, end)
            if j < 0:
                errors.append(f"{path}:{line}: unterminated /* comment inside css``")
                return
            line += src.count("\n", i, j)
            i = j + 2
            continue
        if c in "'\"":
            i = _string_end(src, i)
            continue
        if src.startswith("${", i):
            i = _expr_end(src, i + 2)
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren = max(0, paren - 1)
        elif c == ";":
            if paren > 0:
                errors.append(f"{path}:{line}: `;` inside unclosed `(` — rest of stylesheet is silently dropped")
        elif c == "{":
            if paren > 0:
                errors.append(f"{path}:{line}: `{{` inside unclosed `(`")
            brace += 1
        elif c == "}":
            if paren > 0:
                errors.append(f"{path}:{line}: `}}` inside unclosed `(`")
            brace -= 1
            if brace < 0:
                errors.append(f"{path}:{line}: stray `}}` without matching `{{`")
                brace = 0
        i += 1
    if paren != 0:
        errors.append(f"{path}:{line}: {paren} unclosed `(` at end of css``")
    if brace != 0:
        errors.append(f"{path}:{line}: unbalanced `{{`/`}}` in css`` (delta {brace})")


def _is_css_tag_at(src: str, i: int) -> bool:
    """src[i] — 'c' токена `css` с последующим backtick (tagged template)."""
    if not src.startswith("css`", i):
        return False
    return i == 0 or src[i - 1] not in IDENT_CHARS


def _scan_region(src: str, start: int, end: int, path: str, errors: list[str]) -> None:
    """Обходит регион исходника: пропускает комментарии/строки, находит css``
    и рекурсивно проверяет `${}`-выражения любых шаблонов (внутри них могут
    быть вложенные css``)."""
    n = len(src)
    i = start
    while i < end:
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        c = src[i]
        if c in "'\"":
            i = _string_end(src, i)
            continue
        if c == "c" and _is_css_tag_at(src, i):
            close = _template_end(src, i + 4)
            if close < 0:
                errors.append(f"{path}:{src.count(chr(10), 0, i) + 1}: unterminated css`` template")
                return
            _scan_css(src, i + 4, close, path, errors)
            for span_start, span_end in _iter_expr_spans(src, i + 4, close):
                _scan_region(src, span_start, span_end, path, errors)
            i = close + 1
            continue
        if c == "`":
            close = _template_end(src, i + 1)
            if close < 0:
                return
            for span_start, span_end in _iter_expr_spans(src, i + 1, close):
                _scan_region(src, span_start, span_end, path, errors)
            i = close + 1
            continue
        i += 1


def _scan_file(path: Path, errors: list[str]) -> None:
    src = path.read_text(encoding="utf-8", errors="replace")
    if "css`" not in src:
        return
    _scan_region(src, 0, len(src), path.relative_to(ROOT).as_posix(), errors)


def main() -> int:
    errors: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.ts"):
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            _scan_file(path, errors)
    return report("css_template_balance", errors)


if __name__ == "__main__":
    sys.exit(main())
