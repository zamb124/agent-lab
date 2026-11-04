#!/usr/bin/env python3
"""Статическая проверка автономного embed (внешний сайт без import map).

Embed-бандлы ``core/frontend/embed-dist/**/*.js`` отдаются на чужие origin
целиком: единственные разрешённые импорты — относительные пути к чанкам
того же каталога. Bare-спецификатор (``from 'lit'``) или абсолютный URL
(``import('/static/…')``) в выходе означает утечку несобранного модуля —
на внешнем сайте это ``Failed to resolve module specifier`` или 404.

Источники при этом используют канонические npm-спецификаторы: гарантию
self-contained даёт esbuild, поэтому гейт проверяет собранный выход,
а не дерево исходников.

Запуск:
    uv run python -m scripts.gates.frontend.embed_esm_closure

Вызывается из ``make check-core-frontend-canon`` (слой перед browser-тестами).
Требует свежий ``node scripts/build/ui.ts``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT as ROOT

EMBED_DIST = ROOT / "core" / "frontend" / "embed-dist"

STATIC_IMPORT_RE = re.compile(r"""(?:from|import)\s*['"]([^'"]+)['"]""")
DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")
# Спецификатор модуля: ./x ../x /x https://x или bare (@scope/pkg, pkg/sub).
# Минифицированный код полон похожих подстрок (`,import:`, `,t.from),f.attr(`) —
# без формы спецификатора это не импорт, а фрагмент кода.
SPECIFIER_RE = re.compile(r"^(?:\.{0,2}/|/|https?://|@?[\w-]+(?:/[\w./@-]+)*)[\w./@-]*$")

ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def _code_mask(text: str) -> bytearray:
    """Битовая маска позиций, которые являются кодом (не строкой и не комментарием).

    Бандлы полны учебных строк вида ``import { X } from 'echarts/components'``
    внутри ``error("…")`` и комментариев ``from "extension"`` — без маски
    регулярка ловит их как настоящие импорты. Маска сохраняет offsets, так что
    позиция матча напрямую проверяется на принадлежность коду.
    """
    n = len(text)
    mask = bytearray(n)
    i = 0
    state = "code"  # code | str | line | block
    quote = ""
    stack: list[str] = []  # '{': обычный блок, 'tpl': выражение ${ в template literal
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if state == "code":
            mask[i] = 1
            if c == "/" and nxt == "/":
                i += 2
                state = "line"
                continue
            if c == "/" and nxt == "*":
                i += 2
                state = "block"
                continue
            if c in "'\"`":
                quote = c
                state = "str"
                i += 1
                continue
            if c == "{":
                stack.append("{")
            elif c == "}":
                if stack and stack[-1] == "tpl":
                    _ = stack.pop()
                    quote = "`"
                    state = "str"
                elif stack:
                    _ = stack.pop()
            i += 1
            continue
        if state == "line":
            if c == "\n":
                mask[i] = 1
                state = "code"
            i += 1
            continue
        if state == "block":
            if c == "*" and nxt == "/":
                i += 2
                state = "code"
                continue
            i += 1
            continue
        # state == "str"
        if c == "\\":
            i += 2
            continue
        if quote == "`" and c == "$" and nxt == "{":
            stack.append("tpl")
            i += 2
            state = "code"
            continue
        if c == quote:
            i += 1
            state = "code"
            continue
        i += 1
    return mask


def _check_file(path: Path, text: str) -> None:
    mask = _code_mask(text)
    offset = 0
    for i, line in enumerate(text.splitlines(), start=1):
        matches = [
            *STATIC_IMPORT_RE.finditer(line),
            *DYNAMIC_IMPORT_RE.finditer(line),
        ]
        for match in matches:
            if not mask[offset + match.start()]:
                continue
            spec = match.group(1)
            if not SPECIFIER_RE.match(spec) or spec.startswith("."):
                continue
            kind = "bare specifier" if not spec.startswith(("http://", "https://", "/")) else "external URL"
            fail(
                f"{path.relative_to(ROOT)}:{i}: embed-бандл не self-contained "
                + f"({kind} {spec!r} — на внешнем сайте нет import map)"
            )
        offset += len(line) + 1


def main() -> int:
    if not EMBED_DIST.is_dir():
        fail("embed-dist отсутствует: запустить node scripts/build/ui.ts")
    else:
        js_files = sorted(EMBED_DIST.rglob("*.js"))
        if not js_files:
            fail("embed-dist пуст: запустить node scripts/build/ui.ts")
        for path in js_files:
            if path.suffix != ".js" or path.name.endswith(".map.js"):
                continue
            _check_file(path, path.read_text(encoding="utf-8", errors="replace"))
    if ERRORS:
        for e in ERRORS:
            print(e, file=sys.stderr)
        print(f"\nembed ESM closure: FAIL ({len(ERRORS)} ошибок)", file=sys.stderr)
        return 1
    print("embed ESM closure: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
