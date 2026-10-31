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
Требует свежий ``node scripts/build/ui.mjs``.
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


def _check_file(path: Path, text: str) -> None:
    for i, line in enumerate(text.splitlines(), start=1):
        for spec in STATIC_IMPORT_RE.findall(line) + DYNAMIC_IMPORT_RE.findall(line):
            if not SPECIFIER_RE.match(spec) or spec.startswith("."):
                continue
            kind = "bare specifier" if not spec.startswith(("http://", "https://", "/")) else "external URL"
            fail(
                f"{path.relative_to(ROOT)}:{i}: embed-бандл не self-contained "
                f"({kind} {spec!r} — на внешнем сайте нет import map)"
            )


def main() -> int:
    if not EMBED_DIST.is_dir():
        fail(f"embed-dist отсутствует: запустить node scripts/build/ui.mjs")
    else:
        js_files = sorted(EMBED_DIST.rglob("*.js"))
        if not js_files:
            fail(f"embed-dist пуст: запустить node scripts/build/ui.mjs")
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
