#!/usr/bin/env python3
"""
Сканер UI: строки с кириллицей вне однострочных // и строк JSDoc (*).
Каталоги: apps/<service>/ui/**/*.js (Lit и прочий фронт сервисов).

Примеры:
  uv run python scripts/report_ui_i18n_gaps.py
  uv run python scripts/report_ui_i18n_gaps.py --app crm
  uv run python scripts/report_ui_i18n_gaps.py --summary

Ориентир: видимые строки и литералы вынести в core/i18n/translations/<locale>/{service}.json;
общие слова — common.json (третий аргумент this.i18n.t).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / "apps"

GLOBAL_SKIP_NAMES = frozenset(
    {
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


def skip_file(path: Path) -> bool:
    if path.name in GLOBAL_SKIP_NAMES:
        return True
    if path.name.startswith("debug-"):
        return True
    return False


def scan_ui_dir(ui_dir: Path, root: Path) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    if not ui_dir.is_dir():
        return hits
    for path in sorted(ui_dir.rglob("*.js")):
        if skip_file(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"report_ui_i18n_gaps: не прочитан {path}: {e}", file=sys.stderr)
            raise
        for i, line in enumerate(text.splitlines(), start=1):
            if line_is_comment_only(line):
                continue
            if CYR.search(line):
                hits.append((path.relative_to(root), i, line.rstrip()))
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description="Кириллица в apps/*/ui после фильтра комментариев")
    parser.add_argument(
        "--app",
        type=str,
        default="all",
        help="Имя сервиса (crm, flows, frontend, rag, sync) или all",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Только агрегаты по сервисам, без списка строк",
    )
    args = parser.parse_args()

    if not APPS.is_dir():
        print(f"report_ui_i18n_gaps: нет каталога {APPS}", file=sys.stderr)
        return 1

    service_dirs: list[tuple[str, Path]] = []
    for app_dir in sorted(APPS.iterdir()):
        if not app_dir.is_dir():
            continue
        ui = app_dir / "ui"
        if not ui.is_dir():
            continue
        name = app_dir.name
        if args.app != "all" and name != args.app:
            continue
        service_dirs.append((name, ui))

    if args.app != "all" and not service_dirs:
        print(f"report_ui_i18n_gaps: сервис не найден или нет ui: {args.app}", file=sys.stderr)
        return 1

    all_hits: list[tuple[str, Path, int, str]] = []
    for svc, ui in service_dirs:
        for path, lineno, content in scan_ui_dir(ui, ROOT):
            all_hits.append((svc, path, lineno, content))

    by_svc: dict[str, list[tuple[Path, int, str]]] = {}
    for svc, path, lineno, content in all_hits:
        by_svc.setdefault(svc, []).append((path, lineno, content))

    print("report_ui_i18n_gaps: по сервисам (файлов с совпадениями / строк)")
    for svc, _ui in service_dirs:
        h = by_svc.get(svc, [])
        files = len({p for p, _, _ in h})
        print(f"  {svc}: {files} файлов, {len(h)} строк")
    print(f"report_ui_i18n_gaps: всего файлов {len({p for _, p, _, _ in all_hits})}, строк {len(all_hits)}")
    print("")

    if args.summary:
        return 0

    for svc, path, lineno, content in sorted(all_hits, key=lambda x: (x[0], str(x[1]), x[2])):
        print(f"{path}:{lineno}:{content}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except OSError as e:
        print(f"report_ui_i18n_gaps: {e}", file=sys.stderr)
        raise SystemExit(1)
