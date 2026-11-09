#!/usr/bin/env python3
"""
CI-gate: корень репозитория без дампов, бинарников, ключей и черновиков.

Проверяются и индекс, и рабочее дерево: отслеживаемые файлы корня обязаны входить
в allowlist; любой файл корня на диске с запрещённым расширением (документы, архивы,
дампы, ключи) — FAIL, даже если он в .gitignore; каталоги корня — только из allowlist
(gitignored локальные каталоги инструментов вроде `.venv`, `node_modules` допускаются
явно), чтобы `tmp/`, `site/`, `build/`, `drafts/` не появлялись снова.
"""

from __future__ import annotations

import subprocess
import sys

from scripts.gates.kit import REPO_ROOT

ALLOWED_ROOT_FILES: frozenset[str] = frozenset(
    {
        ".cursorignore",
        ".dockerignore",
        ".editorconfig",
        ".env.example",
        ".env.pytest",
        ".gitattributes",
        ".gitignore",
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
        "tsconfig.base.json",
        "tsconfig.json",
        "uv.lock",
        "vitest.config.ts",
        "web-test-runner.config.ts",
        "web-test-runner.middleware.ts",
        "zensical.en.toml",
        "zensical.ru.toml",
    }
)
# Локальные файлы разработчика: не коммитятся (.gitignore), но допустимы на диске.
ALLOWED_LOCAL_ROOT_FILES: frozenset[str] = frozenset(
    {
        ".DS_Store",
        ".coverage",
        ".env",
        ".env.test-compose-images",
        "build-zensical.en.toml",
        "build-zensical.ru.toml",
        "conf.local.json",
    }
)
ALLOWED_ROOT_DIRS: frozenset[str] = frozenset(
    {
        ".cursor",
        ".github",
        "apps",
        "blog",
        "ci_scripts",
        "conf",
        "core",
        "deploy",
        "docs",
        "migrations",
        "mk",
        "mobile",
        "scripts",
        "tests",
        "typings",
    }
)
# Каталоги, которые пишут инструменты (gitignored): сборки документации, отчёты тестов, кэши.
ALLOWED_GENERATED_ROOT_DIRS: frozenset[str] = frozenset(
    {
        ".cache",
        ".devin",
        ".git",
        ".hypothesis",
        ".idea",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".vscode",
        ".zed",
        "__pycache__",
        "artifacts",
        "build",
        "coverage",
        "data",
        "documentation-dist",
        "node_modules",
        "reports",
        "seo-dist",
    }
)
FORBIDDEN_ROOT_SUFFIXES: tuple[str, ...] = (
    ".pdf", ".docx", ".xlsx", ".pptx", ".zip", ".tar", ".gz", ".sql", ".dump",
    ".p12", ".pem", ".key", ".p8", ".sqlite", ".db", ".log", ".yml",
)
# Имена файлов корня, за которыми стоят ключи/креды вне зависимости от расширения.
FORBIDDEN_ROOT_FILE_NAMES: frozenset[str] = frozenset({"google_service_account.json"})


def _tracked_root_files() -> list[str]:
    out = subprocess.run(["git", "ls-files", "--", "."], cwd=REPO_ROOT, capture_output=True, text=True, check=True)
    return sorted({line for line in out.stdout.split("\n") if line and "/" not in line})


def main() -> int:
    errors: list[str] = []
    tracked = _tracked_root_files()
    for name in tracked:
        if name not in ALLOWED_ROOT_FILES:
            errors.append(f"в индексе лишний файл корня: {name} (перенеси в каталог или добавь в allowlist осознанно)")
    for entry in sorted(REPO_ROOT.iterdir(), key=lambda path: path.name):
        name = entry.name
        if entry.is_dir():
            if name not in ALLOWED_ROOT_DIRS and name not in ALLOWED_GENERATED_ROOT_DIRS:
                errors.append(f"каталог корня вне allowlist: {name}/ (черновики и сборки живут вне корня репозитория)")
            continue
        if entry.suffix.lower() in FORBIDDEN_ROOT_SUFFIXES or name in FORBIDDEN_ROOT_FILE_NAMES:
            errors.append(f"в корне {name}: дампы/документы/ключи не хранятся в репозитории даже локально")
            continue
        if name not in ALLOWED_ROOT_FILES and name not in ALLOWED_LOCAL_ROOT_FILES:
            errors.append(f"файл корня вне allowlist: {name}")
    if errors:
        print("check_repo_hygiene: FAIL")
        for error in errors:
            print(f"  {error}")
        return 1
    print("check_repo_hygiene: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
