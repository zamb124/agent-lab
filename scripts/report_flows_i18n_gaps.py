#!/usr/bin/env python3
"""
Сканер apps/flows/ui: строки с кириллицей вне однострочных // комментариев.
Ориентир для выноса в core/i18n/translations/*/flows.json.
Исключаются debug-файлы и build-mock-config (технические сообщения/моки).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOWS_UI = ROOT / "apps" / "flows" / "ui"

SKIP_NAMES = frozenset(
    {
        "debug-canvas-styles.js",
        "debug-canvas-extended.js",
        "build-mock-config.js",
    }
)

CYR = re.compile(r"[а-яА-ЯёЁ]")


def line_is_comment_only(line: str) -> bool:
    s = line.strip()
    if not s:
        return True
    if s.startswith("//"):
        return True
    if s.startswith("*") or s.startswith("/**") or s.startswith("*/"):
        return True
    return False


def main() -> int:
    if not FLOWS_UI.is_dir():
        print(f"report_flows_i18n_gaps: нет каталога {FLOWS_UI}", file=sys.stderr)
        return 1

    hits: list[tuple[Path, int, str]] = []
    for path in sorted(FLOWS_UI.rglob("*.js")):
        if path.name in SKIP_NAMES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"report_flows_i18n_gaps: не прочитан {path}: {e}", file=sys.stderr)
            return 1
        for i, line in enumerate(text.splitlines(), start=1):
            if line_is_comment_only(line):
                continue
            if CYR.search(line):
                hits.append((path.relative_to(ROOT), i, line.rstrip()))

    print(f"report_flows_i18n_gaps: файлов с совпадениями: {len({p for p, _, _ in hits})}")
    print(f"report_flows_i18n_gaps: строк (после фильтра комментариев): {len(hits)}")
    print("")
    for path, lineno, content in hits:
        print(f"{path}:{lineno}:{content}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
