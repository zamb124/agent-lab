#!/usr/bin/env python3
"""CI gate: unified Files API — zero legacy symbols in apps/ and tests/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

LEGACY_SYMBOLS: tuple[tuple[str, str], ...] = (
    (r"\bFileProcessor\b", "FileProcessor"),
    (r"\bget_default_file_processor\b", "get_default_file_processor"),
    (r"\bbuild_file_api_router\b", "build_file_api_router"),
    (r"\bpersist_uploaded\b", "persist_uploaded"),
    (r"\bupload_namespace_document\b", "upload_namespace_document"),
    (r"\.file_processor\b", "container.file_processor"),
)

FORBIDDEN_FACTORY_NAMES: tuple[str, ...] = (
    "sync/file_upload",
    "flows/file_upload",
    "crm/file_upload",
    "worktracker/file_upload",
    "rag/file_upload",
)

PER_SERVICE_FILES_PATH = re.compile(
    r"/(?:flows|crm|sync|rag|worktracker)/api/v1/files/(?!upload-completed)"
)

SCAN_DIRS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "tests",
)

ALLOWLIST_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "apps" / "crm_worker" / "worker.py",
    REPO_ROOT / "apps" / "crm" / "README.md",
)


def _is_allowlisted(path: Path) -> bool:
    for allowed in ALLOWLIST_PATHS:
        if path.resolve() == allowed.resolve():
            return True
    return False


def _scan_for_legacy() -> list[str]:
    errors: list[str] = []
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".js", ".md", ".mdc"}:
                continue
            if _is_allowlisted(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(REPO_ROOT)
            for pattern, label in LEGACY_SYMBOLS:
                if re.search(pattern, text):
                    errors.append(f"{rel}: forbidden legacy symbol {label}")
            if path.suffix == ".js":
                for factory_name in FORBIDDEN_FACTORY_NAMES:
                    if f"name: '{factory_name}'" in text or f'name: "{factory_name}"' in text:
                        errors.append(f"{rel}: forbidden factory {factory_name}")
            if PER_SERVICE_FILES_PATH.search(text):
                errors.append(f"{rel}: per-service /api/v1/files/ path is forbidden")
    return errors


def _check_single_http_mount() -> list[str]:
    errors: list[str] = []
    factory_path = REPO_ROOT / "core" / "app" / "factory.py"
    text = factory_path.read_text(encoding="utf-8")
    if "build_file_api_router" in text:
        errors.append("core/app/factory.py: build_file_api_router must not be mounted")
    if text.count("build_files_router") < 1:
        errors.append("core/app/factory.py: build_files_router must be used for frontend mount")
    return errors


def main() -> int:
    errors = _scan_for_legacy()
    errors.extend(_check_single_http_mount())
    if errors:
        print("check_files_canon: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    print("check_files_canon: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
