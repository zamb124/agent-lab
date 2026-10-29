#!/usr/bin/env python3
"""
CI-gate: владелец команд ⇔ каталог операций.

1. Каждый owner из `core/realtime/command_owners.py::_OWNER_BY_SCOPE` имеет
   `apps/<svc>/realtime/command_router.py` с непустым `<SVC>_OPERATIONS`.
2. Каждый каталог `<SVC>_OPERATIONS` зарегистрирован владельцем в `_OWNER_BY_SCOPE`
   (иначе команды `<svc>/*_requested` из UI не доедут до `op_*`).
3. Каждый ключ каталога — `<owner>/<entity>/<verb>_requested` своего owner.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

from scripts.gates.kit import REPO_ROOT

APPS_ROOT = REPO_ROOT / "apps"
OWNERS_PATH = REPO_ROOT / "core" / "realtime" / "command_owners.py"


def _owner_map() -> dict[str, str]:
    tree = ast.parse(OWNERS_PATH.read_text(encoding="utf-8"), filename=str(OWNERS_PATH))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "_OWNER_BY_SCOPE" and isinstance(node.value, ast.Dict):
                owners: dict[str, str] = {}
                for key, value in zip(node.value.keys, node.value.values, strict=True):
                    if not isinstance(key, ast.Constant) or not isinstance(value, ast.Constant):
                        raise SystemExit("_OWNER_BY_SCOPE: ожидаются строковые литералы")
                    owners[str(key.value)] = str(value.value)
                return owners
    raise SystemExit(f"{OWNERS_PATH}: _OWNER_BY_SCOPE не найден")


def _catalog_keys(router_path: Path) -> list[str]:
    tree = ast.parse(router_path.read_text(encoding="utf-8"), filename=str(router_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id.endswith("_OPERATIONS") and isinstance(node.value, ast.Dict):
                keys: list[str] = []
                for key in node.value.keys:
                    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
                        raise SystemExit(f"{router_path}: ключи каталога должны быть строками")
                    keys.append(key.value)
                return keys
    raise SystemExit(f"{router_path}: каталог <SVC>_OPERATIONS не найден")


def main() -> int:
    owners = _owner_map()
    errors: list[str] = []
    catalogs: dict[str, list[str]] = {}
    for router_path in sorted(APPS_ROOT.glob("*/realtime/command_router.py")):
        service = router_path.relative_to(APPS_ROOT).parts[0]
        catalogs[service] = _catalog_keys(router_path)

    for scope, owner in owners.items():
        if scope != owner:
            errors.append(f"scope {scope!r} → owner {owner!r}: scope обязан совпадать с именем сервиса")
        keys = catalogs.get(owner)
        if keys is None:
            errors.append(f"owner {owner!r} без apps/{owner}/realtime/command_router.py")
        elif not keys:
            errors.append(f"owner {owner!r}: пустой каталог операций")

    for service, keys in catalogs.items():
        if service not in owners:
            errors.append(f"каталог apps/{service}/realtime/command_router.py без владельца в _OWNER_BY_SCOPE")
        for key in keys:
            if not key.startswith(f"{service}/") or not key.endswith("_requested"):
                errors.append(f"{service}: ключ {key!r} должен быть '{service}/<entity>/<verb>_requested'")

    if errors:
        print("check_command_owner_catalogs: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"check_command_owner_catalogs: OK ({len(owners)} владельцев, {sum(len(v) for v in catalogs.values())} команд)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
