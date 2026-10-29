#!/usr/bin/env python3
"""CI-gate: цепочка ``migrations/<db>/NNNN_<name>.py`` от ``0001_initial.py``.

Каталог ``migrations/<db>/`` совпадает с ``migrations/services.json``.
Рядом допустимы только ``migrations/services.json`` и ``migrations/postgres/init.sql``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from core.types import parse_json_object, require_json_object
from scripts.gates.kit import REPO_ROOT

MIGRATIONS = REPO_ROOT / "migrations"
MANIFEST = MIGRATIONS / "services.json"
ALLOWED_ROOT_FILES = frozenset({"services.json"})
ALLOWED_EXTRA_DIRS = frozenset({"postgres"})
SKIP_DIR_NAMES = frozenset({"__pycache__"})
_MIGRATION_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.py$")


def _relative(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _service_names() -> list[str]:
    raw = parse_json_object(MANIFEST.read_text(encoding="utf-8"), "migrations/services.json")
    services = raw["services"]
    if not isinstance(services, list):
        raise SystemExit("migrations/services.json: services must be a list")
    names: list[str] = []
    for item in services:
        entry = require_json_object(item, "migrations/services.json service")
        name = entry["name"]
        if not isinstance(name, str) or name == "":
            raise SystemExit("migrations/services.json: service name is missing")
        names.append(name)
    return names


def _walk_files(directory: Path) -> list[Path]:
    found: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        if path.is_file():
            found.append(path)
    return found


def migration_chain_errors(directory: Path, *, root: Path) -> list[str]:
    """Ошибки цепочки одного каталога базы. Пустой список — цепочка сплошная от ``0001_initial``."""
    label = directory.relative_to(root).as_posix()
    errors: list[str] = []
    if not directory.is_dir():
        return [f"{label}: directory is missing"]
    files = _walk_files(directory)
    numbers: list[int] = []
    for path in files:
        match = _MIGRATION_FILE.fullmatch(path.name)
        if match is None:
            errors.append(f"{path.relative_to(root).as_posix()}: migration file must be NNNN_<name>.py")
            continue
        numbers.append(int(match.group(1)))
    if directory / "0001_initial.py" not in files:
        errors.append(f"{label}/0001_initial.py: missing")
    expected = list(range(1, len(numbers) + 1))
    if sorted(numbers) != expected:
        errors.append(f"{label}: migration numbers must be 0001..{len(numbers):04d} without gaps")
    return errors


def main() -> int:
    errors: list[str] = []
    if not MANIFEST.is_file():
        print("check_migration_files_canon: migrations/services.json is missing", file=sys.stderr)
        return 1
    names = _service_names()
    expected_dirs = set(names) | set(ALLOWED_EXTRA_DIRS)
    for child in sorted(MIGRATIONS.iterdir()):
        if child.name in SKIP_DIR_NAMES:
            continue
        if child.is_file():
            if child.name not in ALLOWED_ROOT_FILES:
                errors.append(f"{_relative(child)}: migrations root allows only services.json")
            continue
        if child.name not in expected_dirs:
            errors.append(f"{_relative(child)}: directory is not a service database")
    init_sql = MIGRATIONS / "postgres" / "init.sql"
    if not init_sql.is_file():
        errors.append("migrations/postgres/init.sql: missing")
    for path in _walk_files(MIGRATIONS / "postgres"):
        if path != init_sql:
            errors.append(f"{_relative(path)}: postgres/ allows only init.sql")
    for name in names:
        directory = MIGRATIONS / name
        if not directory.is_dir():
            errors.append(f"migrations/{name}: directory is missing")
            continue
        errors.extend(migration_chain_errors(directory, root=MIGRATIONS))
    if errors:
        print("check_migration_files_canon: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1
    print("check_migration_files_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
