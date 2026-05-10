#!/usr/bin/env python3
"""Статическая проверка автономного embed (внешний сайт без import map).

Строится замыкание относительных импортов от entrypoints в
``core/frontend/static/lib/embed-chat/``. Любой файл в замыкании не должен
содержать bare ``from 'lit'`` / ``from 'lit/...`` или ``from '@platform/...``.
Иначе в браузере на чужом origin — ``Failed to resolve module specifier``.

Запуск:
    uv run python scripts/check_embed_esm_closure.py

Вызывается из ``make check-core-frontend-canon`` (слой перед browser-тестами).
"""

from __future__ import annotations

import re
import sys
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_ROOT = ROOT / "core" / "frontend" / "static"
LIB = STATIC_ROOT / "lib"

ENTRYPOINTS = tuple(
    LIB / rel
    for rel in (
        Path("embed-chat/platform-embed-chat-drawer.js"),
        Path("embed-chat/platform-embed-chat.js"),
        Path("embed-chat/platform-lara-assistant.js"),
    )
)

FROM_SPEC_RE = re.compile(r"""\bfrom\s+(['"])([^'"]+)\1""")
IMPORT_SIDE_RE = re.compile(r"""^\s*import\s+['"]([^'"]+)['"]\s*;?\s*$""", re.MULTILINE)

BARE_LIT_RE = re.compile(r"""\bfrom\s+['"]lit(?:/[^'"]*)?['"]""")
BARE_PLATFORM_RE = re.compile(r"""\bfrom\s+['"]@platform/[^'"]+['"]""")

ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def _strip_comments(text: str) -> str:
    def _block(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    text = re.sub(r"/\*.*?\*/", _block, text, flags=re.S)
    text = re.sub(r"(^|[^:\\])//[^\n]*", lambda m: m.group(1), text)
    return text


def _collect_relative_specs(text: str) -> list[str]:
    specs: list[str] = []
    clean = _strip_comments(text)
    for m in FROM_SPEC_RE.finditer(clean):
        specs.append(m.group(2))
    for m in IMPORT_SIDE_RE.finditer(clean):
        specs.append(m.group(1))
    return specs


def _resolve_import(importer: Path, spec: str) -> Path | None:
    if spec.startswith(("http://", "https://")):
        return None
    if not spec.startswith((".", "/")):
        return None
    tgt = (importer.parent / spec).resolve()
    try:
        tgt.relative_to(STATIC_ROOT.resolve())
    except ValueError:
        fail(f"{importer.relative_to(ROOT)}: импорт вне {STATIC_ROOT.name}: {spec!r}")
        return None
    return tgt


def _visit_target(importer: Path, spec: str, tgt: Path) -> Path | None:
    if not tgt.exists():
        fail(f"{importer.relative_to(ROOT)}: нет файла по импорту {spec!r} -> {tgt.relative_to(ROOT)}")
        return None
    if tgt.suffix.lower() != ".js":
        fail(f"{tgt.relative_to(ROOT)}: замыкание embed ожидает только *.js (импорт из {importer.relative_to(ROOT)})")
        return None
    return tgt.resolve()


def _scan_closure() -> None:
    visited: set[Path] = set()
    q: deque[Path] = deque()

    for ep in ENTRYPOINTS:
        if not ep.is_file():
            fail(f"{ep.relative_to(ROOT)}: entrypoint отсутствует")
            continue
        rp = ep.resolve()
        visited.add(rp)
        q.append(rp)

    while q:
        cur = q.popleft()
        raw = cur.read_text(encoding="utf-8")
        clean = _strip_comments(raw)
        if BARE_LIT_RE.search(clean):
            for i, line in enumerate(clean.splitlines(), start=1):
                if BARE_LIT_RE.search(line):
                    fail(
                        f"{cur.relative_to(ROOT)}:{i}: bare import lit "
                        "(нужны относительные пути к assets/js/lit или lit-shim в embed-chat)"
                    )
                    break
        if BARE_PLATFORM_RE.search(clean):
            for i, line in enumerate(clean.splitlines(), start=1):
                if BARE_PLATFORM_RE.search(line):
                    fail(
                        f"{cur.relative_to(ROOT)}:{i}: bare import @platform "
                        "(на внешнем сайте нужен только ./ ../ к статике)"
                    )
                    break

        for spec in _collect_relative_specs(raw):
            tgt = _resolve_import(cur, spec)
            if tgt is None:
                continue
            resolved = _visit_target(cur, spec, tgt)
            if resolved is None:
                continue
            if resolved in visited:
                continue
            visited.add(resolved)
            q.append(resolved)


def main() -> int:
    _scan_closure()
    if ERRORS:
        for e in ERRORS:
            print(e, file=sys.stderr)
        print(f"\nembed ESM closure: FAIL ({len(ERRORS)} ошибок)", file=sys.stderr)
        return 1
    print("embed ESM closure: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
