"""Корень scripts/ — только пакеты; у гейтов нет префикса check_/test_/generate_."""

from __future__ import annotations

from scripts.gates.kit import REPO_ROOT, report

_SCRIPTS = REPO_ROOT / "scripts"
_ROOT_FILES = frozenset({"__init__.py"})
_FORBIDDEN_PREFIXES = ("check_", "test_", "generate_")
_SKIP_DIR_NAMES = frozenset({"__pycache__", "stress"})


def collect_errors() -> list[str]:
    errors: list[str] = []
    for path in sorted(_SCRIPTS.iterdir()):
        if path.name.startswith("."):
            continue
        if path.is_file() and path.name not in _ROOT_FILES:
            errors.append(f"scripts/{path.name}: file does not belong at scripts/ root")
    for path in sorted(_SCRIPTS.rglob("*.py")):
        if _SKIP_DIR_NAMES.intersection(path.parts):
            continue
        if path.name.startswith(_FORBIDDEN_PREFIXES):
            errors.append(f"{path.relative_to(REPO_ROOT).as_posix()}: rename without check_/test_/generate_")
    for directory in sorted(path for path in _SCRIPTS.rglob("*") if path.is_dir()):
        relative = directory.relative_to(_SCRIPTS)
        if not relative.parts or _SKIP_DIR_NAMES.intersection(relative.parts):
            continue
        if directory.name == "__pycache__":
            continue
        if not (directory / "__init__.py").is_file():
            errors.append(f"{directory.relative_to(REPO_ROOT).as_posix()}: missing __init__.py")
    return errors


def main() -> int:
    return report("scripts_layout", collect_errors())


if __name__ == "__main__":
    raise SystemExit(main())
