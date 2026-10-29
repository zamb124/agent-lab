#!/usr/bin/env python3
"""
CI-gate: ошибки границы без RU-хардкода.

1. `platform.json` ru/en: секция `errors` — одинаковые ключи, непустые строки.
2. `WsCommandError(...)` в `apps/` и `core/` обязан иметь keyword `error_code`.
3. Кириллица в аргументах `raise` и `raise_*` / `Platform*Error` / `WsCommandError` —
   ratchet (`scripts/gates/backend/backend_error_i18n_baseline.json`).
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT

SCAN_ROOTS = (REPO_ROOT / "apps", REPO_ROOT / "core")
SKIP_PARTS: frozenset[str] = frozenset({"vendor", "__pycache__", "desktop", "node_modules"})
RU_PLATFORM = REPO_ROOT / "core" / "i18n" / "translations" / "ru" / "platform.json"
EN_PLATFORM = REPO_ROOT / "core" / "i18n" / "translations" / "en" / "platform.json"
BASELINE_PATH = REPO_ROOT / "scripts" / "gates" / "backend" / "backend_error_i18n_baseline.json"
_CYRILLIC_RE_RANGE = ("\u0400", "\u04ff")


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        for path in sorted(root.rglob("*.py")):
            if SKIP_PARTS & set(path.parts):
                continue
            files.append(path)
    return files


def _load_errors_section(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path}: ожидается JSON-объект")
    errors = raw.get("errors")
    if not isinstance(errors, dict):
        raise SystemExit(f"{path}: секция errors обязательна")
    result: dict[str, str] = {}
    for key, value in errors.items():
        if not isinstance(key, str) or not key:
            raise SystemExit(f"{path}: ключ errors должен быть непустой строкой")
        if not isinstance(value, str) or not value:
            raise SystemExit(f"{path}: errors.{key} должен быть непустой строкой")
        result[key] = value
    return result


def _check_error_catalog() -> list[str]:
    ru = _load_errors_section(RU_PLATFORM)
    en = _load_errors_section(EN_PLATFORM)
    failures: list[str] = []
    ru_keys = set(ru)
    en_keys = set(en)
    only_ru = sorted(ru_keys - en_keys)
    only_en = sorted(en_keys - ru_keys)
    if only_ru:
        failures.append(f"errors только в ru: {', '.join(only_ru)}")
    if only_en:
        failures.append(f"errors только в en: {', '.join(only_en)}")
    return failures


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _has_error_code_keyword(call: ast.Call) -> bool:
    return any(keyword.arg == "error_code" for keyword in call.keywords)


def _string_has_cyrillic(value: str) -> bool:
    return any(_CYRILLIC_RE_RANGE[0] <= char <= _CYRILLIC_RE_RANGE[1] for char in value)


def _node_cyrillic_hits(node: ast.AST) -> list[str]:
    hits: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            if _string_has_cyrillic(child.value):
                hits.append(child.value)
    return hits


def _raise_exc_node(node: ast.Raise) -> ast.AST | None:
    if node.exc is None:
        return None
    return node.exc


_RAISE_HELPERS: frozenset[str] = frozenset(
    {
        "raise_invalid",
        "raise_not_found",
        "raise_forbidden",
        "raise_conflict",
        "raise_unavailable",
        "raise_internal",
        "raise_upstream",
        "WsCommandError",
        "PlatformNotFoundError",
        "PlatformConflictError",
        "PlatformAccessDeniedError",
        "PlatformUnavailableError",
        "PlatformBoundaryError",
    }
)


def scan_source(path: Path, source: str) -> tuple[list[str], list[tuple[int, str]]]:
    tree = ast.parse(source, filename=str(path))
    missing_error_code: list[str] = []
    cyrillic_by_line: dict[int, str] = {}
    rel = path.relative_to(REPO_ROOT).as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) == "WsCommandError":
            if not _has_error_code_keyword(node):
                missing_error_code.append(f"{rel}:{node.lineno}")
        if isinstance(node, ast.Raise):
            exc = _raise_exc_node(node)
            if exc is not None:
                hits = _node_cyrillic_hits(exc)
                if hits:
                    cyrillic_by_line.setdefault(node.lineno, hits[0][:80])
        if isinstance(node, ast.Call) and _call_name(node.func) in _RAISE_HELPERS:
            hits = _node_cyrillic_hits(node)
            if hits:
                cyrillic_by_line.setdefault(node.lineno, hits[0][:80])
    return missing_error_code, [(lineno, preview) for lineno, preview in sorted(cyrillic_by_line.items())]


def collect() -> tuple[list[str], list[str]]:
    missing: list[str] = []
    cyrillic_lines: list[str] = []
    for path in _iter_python_files():
        source = path.read_text(encoding="utf-8")
        file_missing, file_cyrillic = scan_source(path, source)
        missing.extend(file_missing)
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, preview in file_cyrillic:
            cyrillic_lines.append(f"{rel}:{lineno}: {preview}")
    return missing, cyrillic_lines


def _load_baseline() -> dict[str, int]:
    if not BASELINE_PATH.exists():
        raise SystemExit(f"{BASELINE_PATH}: нет baseline — запусти --update")
    raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{BASELINE_PATH}: ожидается JSON-объект")
    count = raw.get("cyrillic_raise")
    if not isinstance(count, int):
        raise SystemExit(f"{BASELINE_PATH}: cyrillic_raise должен быть int")
    return {"cyrillic_raise": count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument(
        "--update",
        action="store_true",
        help="записать текущий cyrillic_raise как baseline",
    )
    args = parser.parse_args()
    failures = _check_error_catalog()
    missing, cyrillic_lines = collect()
    cyrillic_count = len(cyrillic_lines)
    if args.update:
        BASELINE_PATH.write_text(
            json.dumps({"cyrillic_raise": cyrillic_count}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"check_backend_error_i18n: baseline cyrillic_raise={cyrillic_count}")
        if missing:
            print("check_backend_error_i18n: FAIL — WsCommandError без error_code=")
            for line in missing[:50]:
                print(f"  {line}")
            if len(missing) > 50:
                print(f"  … ещё {len(missing) - 50}")
            return 1
        if failures:
            print("check_backend_error_i18n: FAIL — каталог errors:")
            for line in failures:
                print(f"  {line}")
            return 1
        return 0

    baseline = _load_baseline()
    allowed = baseline["cyrillic_raise"]
    if missing:
        failures.append(f"WsCommandError без error_code= ({len(missing)})")
        for line in missing[:40]:
            failures.append(f"  {line}")
        if len(missing) > 40:
            failures.append(f"  … ещё {len(missing) - 40}")
    if cyrillic_count > allowed:
        failures.append(
            f"cyrillic_raise: {cyrillic_count} > {allowed} — кириллица в аргументах raise"
        )
        for line in cyrillic_lines[:20]:
            failures.append(f"  {line}")
        if cyrillic_count > 20:
            failures.append(f"  … ещё {cyrillic_count - 20}")
    elif cyrillic_count < allowed:
        print(
            f"check_backend_error_i18n: cyrillic_raise снизился "
            f"{cyrillic_count} < {allowed}, зафиксируй `--update`"
        )
    if failures:
        print("check_backend_error_i18n: FAIL")
        for line in failures:
            print(f"  {line}")
        return 1
    print(
        f"check_backend_error_i18n: OK (errors keys={len(_load_errors_section(EN_PLATFORM))}, "
        f"cyrillic_raise={cyrillic_count})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
