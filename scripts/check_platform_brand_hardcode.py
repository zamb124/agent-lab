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
    REPO_ROOT / "core" / "ai" / "providers" / "__init__.py",
    REPO_ROOT / "core" / "ai" / "providers" / "specs.py",
    REPO_ROOT / "core" / "frontend" / "pwa" / "manifest.json",
    REPO_ROOT / "core" / "frontend" / "pwa" / "sw.js",
)

BRAND_LITERAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'''["']Humanitec["']'''),
    re.compile(r'''["']HumanitecAgent["']'''),
    re.compile(r'''["']Humanitec Models["']'''),
    re.compile(r'''["']Humanitec Voice["']'''),
    re.compile(r'''["']Humanitec LLMs["']'''),
    re.compile(r'''["']Humanitec Flows["']'''),
    re.compile(r'''["']Humanitec Search["']'''),
    re.compile(r'''["']Humanitec Docs["']'''),
    re.compile(r'''["']Humanitec Platform["']'''),
    re.compile(r"\bHUMANITEC\b"),
)

I18N_BRAND_LITERAL_PATTERN = re.compile(r"Humanitec")

BRAND_LITERAL_LINE_ALLOWLIST_SUBSTRINGS: tuple[str, ...] = (
    "humanitec_llm",
    "humanitec://",
    "humanitec-static",
    "humanitec-dynamic",
    "humanitec-metadata",
    "humanitec-web-push",
    "HumanitecDistroConfig",
    "HumanitecModels",
    "deleteObsoleteHumanitecCaches",
    "deleteHumanitecContentCaches",
    "__PLATFORM_NAME__",
    "{platformName}",
    "{agentProductName}",
    "{modelsProductName}",
    "{voiceProductName}",
    "{llmsDisplayLabel}",
    "{flowsProductLabel}",
    "product_humanitec_agent",
    "humanitec_llms_",
    "dashboardHumanitecModels",
    "HumanitecModelsApp",
    "HumanitecModelsSidebar",
    "humanitec-embed-autoload",
    "хуманитэк",
    "agents-lab.ru",
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


def _line_allowed_for_brand_literal(line: str) -> bool:
    return any(marker in line for marker in BRAND_LITERAL_LINE_ALLOWLIST_SUBSTRINGS)


def _scan_i18n_brand_literals() -> list[str]:
    errors: list[str] = []
    translations_root = REPO_ROOT / "core" / "i18n" / "translations"
    if not translations_root.is_dir():
        return errors
    for path in translations_root.rglob("*.json"):
        if path.name.startswith("_"):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        rel = path.relative_to(REPO_ROOT)
        for line_no, line in enumerate(lines, start=1):
            if _line_allowed_for_brand_literal(line):
                continue
            if I18N_BRAND_LITERAL_PATTERN.search(line):
                errors.append(f"{rel}:{line_no}: hardcoded brand literal in i18n JSON")
    return errors


def _scan_brand_literals() -> list[str]:
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
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            rel = path.relative_to(REPO_ROOT)
            for line_no, line in enumerate(lines, start=1):
                if _line_allowed_for_brand_literal(line):
                    continue
                for pattern in BRAND_LITERAL_PATTERNS:
                    if pattern.search(line):
                        errors.append(
                            f"{rel}:{line_no}: hardcoded brand literal {pattern.pattern!r}"
                        )
                        break
    return errors


def main() -> int:
    errors = _scan()
    errors.extend(_scan_html_apex())
    errors.extend(_scan_i18n_product_meta())
    errors.extend(_scan_i18n_brand_literals())
    errors.extend(_scan_brand_literals())
    if errors:
        print("check_platform_brand_hardcode: FAIL", file=sys.stderr)
        for line in errors:
            print(f"  {line}", file=sys.stderr)
        return 1
    print("check_platform_brand_hardcode: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
