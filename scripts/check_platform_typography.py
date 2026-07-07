#!/usr/bin/env python3
"""Platform typography canon: manifest, tokens import, forbidden hardcoded fonts."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import TypedDict, cast

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "core/frontend/static/assets/fonts/platform-typography.json"
TOKENS_PATH = ROOT / "core/frontend/static/assets/css/tokens.css"
FONTS_CSS_PATH = ROOT / "core/frontend/static/assets/fonts/platform-fonts.css"
FONTS_DIR = ROOT / "core/frontend/static/assets/fonts"
RESET_PATH = ROOT / "core/frontend/static/assets/css/reset.css"

SPA_SHELLS = (
    ROOT / "apps/frontend/ui/index.html",
    ROOT / "apps/flows/ui/index.html",
    ROOT / "apps/sync/ui/index.html",
    ROOT / "apps/crm/ui/index.html",
    ROOT / "apps/rag/ui/index.html",
    ROOT / "apps/office/ui/index.html",
    ROOT / "apps/worktracker/ui/index.html",
    ROOT / "apps/provider_litserve/ui/index.html",
)

PLATFORM_HTML = (
    ROOT / "core/frontend/pwa/offline.html",
    ROOT / "apps/agent/desktop/branding/humanitec-pairing.html",
)

SCAN_DIRS = (
    ROOT / "apps",
    ROOT / "core/frontend/static/lib",
    ROOT / "core/frontend/pwa",
    ROOT / "apps/agent/desktop/branding",
)

SCAN_SUFFIXES = {".js", ".css", ".html"}

SKIP_DIR_NAMES = {
    "vendor",
    "node_modules",
    "design",
    "mermaid",
    ".lighthouseci",
}

FORBIDDEN_FONT_LITERALS = (
    "Fira Sans",
    "Onest",
    "SF Pro Display",
    "Geist",
)

FORBIDDEN_LEGACY_TOKENS = (
    "--font-main",
    "--font-condensed",
)

FORBIDDEN_MONO_STACK_PARTS = (
    "ui-monospace",
    "SFMono-Regular",
    "Menlo",
    "Monaco",
    "Consolas",
    "Liberation Mono",
    "Courier New",
)

FONT_FAMILY_RE = re.compile(
    r"font-family\s*:\s*(['\"])([^'\"]+)\1",
    re.IGNORECASE,
)

FONT_FAMILY_UNQUOTED_RE = re.compile(
    r"font-family\s*:\s*([^;{}\n]+)",
    re.IGNORECASE,
)

FONT_SHORTHAND_RE = re.compile(
    r"\bfont\s*:\s*[^;]+",
    re.IGNORECASE,
)

FONT_FAMILY_JS_RE = re.compile(
    r"\.fontFamily\s*=\s*['\"]([^'\"]+)['\"]",
)

ALLOWLIST_SUFFIXES = (
    "/design/design.css",
)

ALLOWLIST_FILES = {
    FONTS_CSS_PATH,
    TOKENS_PATH,
}


class TypographyFace(TypedDict):
    path: str
    weight: str
    style: str


class TypographyRole(TypedDict):
    family: str
    license: str
    faces: list[TypographyFace]


class TypographyStacks(TypedDict):
    sans: str
    mono: str


class PlatformTypographyManifest(TypedDict):
    sans: TypographyRole
    mono: TypographyRole
    stacks: TypographyStacks
    features: dict[str, str]


def _fail(errors: list[str], message: str) -> None:
    errors.append(message)


def _load_manifest() -> PlatformTypographyManifest:
    return cast(
        PlatformTypographyManifest,
        json.loads(MANIFEST_PATH.read_text(encoding="utf-8")),
    )


def _rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _is_scannable(path: Path) -> bool:
    if path.suffix not in SCAN_SUFFIXES:
        return False
    if any(part in SKIP_DIR_NAMES for part in path.parts):
        return False
    if path in ALLOWLIST_FILES:
        return False
    rel = path.as_posix()
    return not any(rel.endswith(suffix) for suffix in ALLOWLIST_SUFFIXES)


def _check_manifest_files(manifest: PlatformTypographyManifest, errors: list[str]) -> None:
    for role in ("sans", "mono"):
        block = manifest[role]
        for face in block["faces"]:
            rel_path = face["path"]
            file_path = FONTS_DIR / rel_path
            if not file_path.is_file():
                _fail(errors, f"platform-typography.json: missing font file {rel_path}")


def _check_tokens_import(manifest: PlatformTypographyManifest, errors: list[str]) -> None:
    tokens_text = TOKENS_PATH.read_text(encoding="utf-8")
    if "@import url('../fonts/platform-fonts.css');" not in tokens_text:
        _fail(errors, "tokens.css must @import ../fonts/platform-fonts.css")

    expected_sans = manifest["stacks"]["sans"]
    expected_mono = manifest["stacks"]["mono"]

    sans_match = re.search(r"--font-sans:\s*([^;]+);", tokens_text)
    mono_match = re.search(r"--font-mono:\s*([^;]+);", tokens_text)
    if sans_match is None:
        _fail(errors, "tokens.css: missing --font-sans")
    elif sans_match.group(1).strip() != expected_sans:
        _fail(
            errors,
            "tokens.css --font-sans must match platform-typography.json stacks.sans",
        )
    if mono_match is None:
        _fail(errors, "tokens.css: missing --font-mono")
    elif mono_match.group(1).strip() != expected_mono:
        _fail(
            errors,
            "tokens.css --font-mono must match platform-typography.json stacks.mono",
        )

    if "--font-feature-sans:" not in tokens_text:
        _fail(errors, "tokens.css: missing --font-feature-sans")

    reset_text = RESET_PATH.read_text(encoding="utf-8")
    if "font-family: var(--font-sans);" not in reset_text:
        _fail(errors, "reset.css body must use font-family: var(--font-sans)")
    if "font-feature-settings: var(--font-feature-sans);" not in reset_text:
        _fail(errors, "reset.css body must use font-feature-settings: var(--font-feature-sans)")


def _check_platform_fonts_css(manifest: PlatformTypographyManifest, errors: list[str]) -> None:
    css_text = FONTS_CSS_PATH.read_text(encoding="utf-8")
    sans_family = manifest["sans"]["family"]
    mono_family = manifest["mono"]["family"]
    if f"font-family: '{sans_family}'" not in css_text:
        _fail(errors, "platform-fonts.css must declare sans family from manifest")
    if f"font-family: '{mono_family}'" not in css_text:
        _fail(errors, "platform-fonts.css must declare mono family from manifest")
    if "font-display: swap" not in css_text:
        _fail(errors, "platform-fonts.css must set font-display: swap")


def _check_html_shell(path: Path, errors: list[str], *, require_tokens: bool) -> None:
    if not path.is_file():
        _fail(errors, f"missing HTML shell {_rel(path)}")
        return
    text = path.read_text(encoding="utf-8")
    if "@font-face" in text:
        _fail(errors, f"{_rel(path)}: local @font-face forbidden — use tokens.css import")
    if "fira-sans" in text.lower():
        _fail(errors, f"{_rel(path)}: fira-sans link forbidden")
    if "fonts.google" in text.lower():
        _fail(errors, f"{_rel(path)}: external Google Fonts forbidden")
    if require_tokens and "/static/core/assets/css/tokens.css" not in text:
        _fail(errors, f"{_rel(path)}: must link /static/core/assets/css/tokens.css")


def _check_spa_shells(errors: list[str]) -> None:
    for shell_path in SPA_SHELLS:
        _check_html_shell(shell_path, errors, require_tokens=True)


def _check_platform_html(manifest: PlatformTypographyManifest, errors: list[str]) -> None:
    offline_path = ROOT / "core/frontend/pwa/offline.html"
    _check_html_shell(offline_path, errors, require_tokens=True)
    offline_text = offline_path.read_text(encoding="utf-8")
    if "var(--font-sans)" not in offline_text:
        _fail(errors, "core/frontend/pwa/offline.html must use var(--font-sans)")

    pairing_path = ROOT / "apps/agent/desktop/branding/humanitec-pairing.html"
    if not pairing_path.is_file():
        _fail(errors, "missing apps/agent/desktop/branding/humanitec-pairing.html")
        return
    pairing_text = pairing_path.read_text(encoding="utf-8")
    expected_stack = manifest["stacks"]["sans"]
    if expected_stack not in pairing_text:
        _fail(
            errors,
            "humanitec-pairing.html must use manifest stacks.sans (desktop offline shell)",
        )


def _contains_forbidden_literal(value: str) -> str | None:
    for forbidden in FORBIDDEN_FONT_LITERALS:
        if forbidden in value:
            return forbidden
    return None


def _is_allowed_font_family(value: str) -> bool:
    stripped = value.strip()
    if stripped in {"inherit", "initial", "unset", "revert"}:
        return True
    if stripped.startswith("var(--font-sans") or stripped.startswith("var(--font-mono"):
        return True
    return False


def _check_font_family_value(path: Path, value: str, errors: list[str]) -> None:
    if _is_allowed_font_family(value):
        if "var(--font-mono," in value or "var(--font-sans," in value:
            _fail(
                errors,
                f"{_rel(path)}: font-family fallback on platform token forbidden — use var(--font-mono) or var(--font-sans)",
            )
        return

    forbidden = _contains_forbidden_literal(value)
    if forbidden is not None:
        _fail(
            errors,
            f"{_rel(path)}: legacy font-family '{value}' ({forbidden}) — use var(--font-sans) or var(--font-mono)",
        )
        return

    lowered = value.lower()
    if "system-ui" in lowered and "var(--font-sans" not in lowered:
        _fail(
            errors,
            f"{_rel(path)}: hardcoded system-ui stack '{value}' — use var(--font-sans)",
        )
        return

    if lowered.strip() == "monospace":
        _fail(
            errors,
            f"{_rel(path)}: bare monospace forbidden — use var(--font-mono)",
        )
        return

    for mono_part in FORBIDDEN_MONO_STACK_PARTS:
        if mono_part.lower() in lowered:
            _fail(
                errors,
                f"{_rel(path)}: legacy mono stack '{value}' — use var(--font-mono)",
            )
            return

    if "'" in value or '"' in value:
        _fail(
            errors,
            f"{_rel(path)}: hardcoded font-family '{value}' — use var(--font-sans) or var(--font-mono)",
        )


def _scan_file(path: Path, errors: list[str]) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")

    for legacy_token in FORBIDDEN_LEGACY_TOKENS:
        if legacy_token in text:
            _fail(
                errors,
                f"{_rel(path)}: legacy typography token {legacy_token} forbidden",
            )

    if "fira-sans" in text.lower():
        _fail(errors, f"{_rel(path)}: fira-sans reference forbidden")

    if path.suffix in {".css", ".html"} and "@font-face" in text:
        _fail(
            errors,
            f"{_rel(path)}: @font-face allowed only in core/frontend/static/assets/fonts/platform-fonts.css",
        )

    for match in FONT_FAMILY_RE.finditer(text):
        _check_font_family_value(path, match.group(2), errors)

    for match in FONT_FAMILY_UNQUOTED_RE.finditer(text):
        raw_value = match.group(1).strip()
        if raw_value.startswith("var("):
            _check_font_family_value(path, raw_value, errors)

    for match in FONT_SHORTHAND_RE.finditer(text):
        shorthand = match.group(0)
        if "var(--font-mono," in shorthand or "var(--font-sans," in shorthand:
            _fail(
                errors,
                f"{_rel(path)}: font shorthand must not add fallbacks to --font-sans/--font-mono",
            )
        forbidden = _contains_forbidden_literal(shorthand)
        if forbidden is not None:
            _fail(
                errors,
                f"{_rel(path)}: legacy font shorthand ({forbidden}) — use typography tokens",
            )

    for match in FONT_FAMILY_JS_RE.finditer(text):
        js_value = match.group(1)
        if js_value.startswith("var("):
            continue
        if "getPropertyValue('--font-sans')" in text or "sansStack" in text:
            continue
        _fail(
            errors,
            f"{_rel(path)}: JS fontFamily literal '{js_value}' forbidden — read --font-sans from computed style",
        )


def _scan_tree(errors: list[str]) -> None:
    for base in SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file() or not _is_scannable(path):
                continue
            _scan_file(path, errors)


def main() -> int:
    errors: list[str] = []
    manifest = _load_manifest()
    _check_manifest_files(manifest, errors)
    _check_tokens_import(manifest, errors)
    _check_platform_fonts_css(manifest, errors)
    _check_spa_shells(errors)
    _check_platform_html(manifest, errors)
    _scan_tree(errors)

    if errors:
        print("check_platform_typography: FAIL", file=sys.stderr)
        for item in errors:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("check_platform_typography: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
