"""Запрещённые пути: components.py процесса, клиенты flows, каталог db office."""

from __future__ import annotations

from scripts.gates.kit import REPO_ROOT, report

_FORBIDDEN_DIRS = (
    "apps/flows/src/clients",
    "apps/office/db",
)


def collect_errors() -> list[str]:
    errors: list[str] = []
    for path in sorted((REPO_ROOT / "apps").glob("*/components.py")):
        errors.append(path.relative_to(REPO_ROOT).as_posix())
    for relative in _FORBIDDEN_DIRS:
        if (REPO_ROOT / relative).exists():
            errors.append(f"{relative}: path is forbidden")
    return errors


def main() -> int:
    return report("forbidden_paths", collect_errors())


if __name__ == "__main__":
    raise SystemExit(main())
