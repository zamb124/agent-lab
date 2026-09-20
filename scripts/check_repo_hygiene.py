#!/usr/bin/env python3
"""
CI-gate: корень репозитория без дампов, бинарников и черновиков.

Отслеживаемые файлы верхнего уровня обязаны входить в allowlist; запрещённые
расширения (документы, архивы, дампы, ключи) в индексе корня — FAIL.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
    {
        ".cursorignore",
        ".dockerignore",
        ".editorconfig",
        ".env.example",
        ".env.pytest",
        ".gitattributes",
        ".gitignore",
        ".gitmodules",
        ".python-version",
        ".rgignore",
        "AGENTS.md",
        "Dockerfile",
        "Dockerfile.base",
        "Dockerfile.base.gpu",
        "Dockerfile.gpu",
        "Dockerfile.test",
        "Dockerfile.test.base",
        "LICENSE",
        "Makefile",
        "README.md",
        "THIRD_PARTY_NOTICES.md",
        "analyze_imports.py",
        "conf.json",
        "conf.local.json.example",
        "doc-sources.md",
        "docker-compose-dev.yaml",
        "docker-compose-test.yaml",
        "mprocs.yaml",
        "package-lock.json",
        "package.json",
        "pyproject.toml",
        "pytest.ini",
        "uv.lock",
        "vitest.config.mjs",
        "web-test-runner.config.mjs",
        "web-test-runner.middleware.mjs",
        "zensical.en.toml",
        "zensical.ru.toml",
    }
)
FORBIDDEN_ROOT_SUFFIXES: tuple[str, ...] = (
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz", ".sql", ".dump",
    ".p12", ".pem", ".key", ".sqlite", ".db", ".log", ".yml",
)


def _tracked_root_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", "."], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return sorted({line for line in out.stdout.split("\n") if line and "/" not in line})


def main() -> int:
    errors: list[str] = []
    for name in _tracked_root_files():
        if name not in ALLOWED_ROOT_FILES:
            errors.append(f"в индексе лишний файл корня: {name} (перенеси в каталог или добавь в allowlist осознанно)")
    for name in _tracked_root_files():
        if Path(name).suffix.lower() in FORBIDDEN_ROOT_SUFFIXES:
            errors.append(f"в индексе {name}: дампы/документы/ключи не коммитятся")
    if errors:
        print("check_repo_hygiene: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    print("check_repo_hygiene: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
