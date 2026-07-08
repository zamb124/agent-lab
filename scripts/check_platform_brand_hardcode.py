#!/usr/bin/env python3
"""CI gate: запрет hardcoded platform apex в runtime-коде apps/ и core/."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

APEX_PATTERN = re.compile(
    r"https?://(?:[a-z0-9-]+\.)?(?:humanitec\.ru|agents-lab\.ru|linnex\.io)(?:[:/]|['\"])",
    re.IGNORECASE,
)

SCAN_ROOTS = (
    REPO_ROOT / "apps",
    REPO_ROOT / "core",
)

SKIP_DIR_NAMES = frozenset(
    {
        "desktop",
        "vendor",
        "node_modules",
        ".vite",
        "dist",
        "out",
    }
)

ALLOWLIST_SUFFIXES = frozenset({".py", ".js", ".html"})

HTML_ALLOWLIST_SUBSTRINGS = (
    "application/ld+json",
    "inline brand inject",
)

I18N_META_PATTERN = re.compile(r'"meta_title":\s*"[^"]*\|\s*Humanitec"')

ALLOWLIST_PATHS: tuple[Path, ...] = (
    REPO_ROOT / "core" / "config" / "base.py",
    REPO_ROOT / "core" / "config" / "models.py",
    REPO_ROOT / "core" / "utils" / "domain.py",
    REPO_ROOT / "core" / "utils" / "subdomain.py",
    REPO_ROOT / "core" / "models" / "identity_models.py",
    REPO_ROOT / "core" / "clients" / "pravo.py",
)


def _is_allowlisted(path: Path) -> bool:
    resolved = path.resolve()
    for allowed in ALLOWLIST_PATHS:
        if resolved == allowed.resolve():
            return True
    return False


def _scan() -> list[str]:
    errors: list[str] = []
    for root in SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIR_NAMES for part in path.parts):
                continue
            if path.suffix not in ALLOWLIST_SUFFIXES:
                continue
            if _is_allowlisted(path):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for match in APEX_PATTERN.finditer(text):
                rel = path.relative_to(REPO_ROOT)
                snippet = match.group(0)[:80]
                errors.append(f"{rel}: hardcoded platform apex URL {snippet!r}")
    return errors


def _scan_html_apex() -> list[str]:
    errors: list[str] = []
    for path in (REPO_ROOT / "apps").rglob("index.html"):
        if any(part in SKIP_DIR_NAMES for part in path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if any(marker in text for marker in HTML_ALLOWLIST_SUBSTRINGS):
            continue
        for match in APEX_PATTERN.finditer(text):
            rel = path.relative_to(REPO_ROOT)
            snippet = match.group(0)[:80]
            errors.append(f"{rel}: hardcoded platform apex URL in HTML {snippet!r}")
    return errors


def _scan_i18n_product_meta() -> list[str]:
    errors: list[str] = []
    for path in (REPO_ROOT / "core" / "i18n" / "translations").rglob("frontend_products.json"):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if I18N_META_PATTERN.search(text):
            rel = path.relative_to(REPO_ROOT)
            errors.append(f"{rel}: meta_title still contains hardcoded '| Humanitec'")
    return errors


def main() -> int:
    errors = _scan()
    errors.extend(_scan_html_apex())
    errors.extend(_scan_i18n_product_meta())
    if errors:
        print("check_platform_brand_hardcode: FAIL", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("check_platform_brand_hardcode: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
