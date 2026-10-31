#!/usr/bin/env python3
"""CI gates #30-33: UI Kit Documentation System (UIKDS) catalog ↔ filesystem."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from scripts.gates.kit import REPO_ROOT as ROOT

DS_ROOT = ROOT / "tests" / "ui" / "design-system"
CATALOG_PATH = DS_ROOT / "catalog.yaml"
MANIFEST_SCHEMA_PATH = DS_ROOT / "manifest.schema.json"
LIB_COMPONENTS = ROOT / "core" / "frontend" / "static" / "lib" / "components"

REQUIRED_FILES = ("README.md", "README.en.md", "manifest.yaml", "playwright.spec.py")
CONTRACT_SPEC_NAMES = ("contract.spec.ts", "contract.spec.js")

_DEFINE_RE = re.compile(
    r"customElements\.define\s*\(\s*['\"](platform-[a-z0-9-]+)['\"]",
    re.MULTILINE,
)

ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def _load_manifest_schema() -> dict[str, object]:
    raw = json.loads(MANIFEST_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("manifest.schema.json must be a JSON object")
    return raw


def _validate_manifest_schema(manifest: dict[str, object], schema: dict[str, object], path: Path) -> None:
    required = schema.get("required")
    if not isinstance(required, list):
        raise ValueError("manifest schema missing required list")
    for key in required:
        if key not in manifest:
            fail(f"{path}: manifest.yaml missing required key {key!r}")


def _discover_registered_components() -> set[str]:
    names: set[str] = set()
    for path in sorted(p for g in ("*.js", "*.ts") for p in LIB_COMPONENTS.rglob(g)):
        text = path.read_text(encoding="utf-8")
        for match in _DEFINE_RE.finditer(text):
            names.add(match.group(1))
    if not names:
        fail("no platform-* customElements.define found under core/frontend/static/lib/components")
    return names


def _load_catalog() -> dict[str, object]:
    if not CATALOG_PATH.is_file():
        fail(f"missing catalog: {CATALOG_PATH}")
        return {"components": []}
    raw = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        fail("catalog.yaml root must be a mapping")
        return {"components": []}
    return raw


def main() -> int:
    schema = _load_manifest_schema()
    catalog = _load_catalog()
    entries = catalog.get("components")
    if not isinstance(entries, list):
        fail("catalog.yaml components must be a list")
        return 1

    catalog_by_name: dict[str, dict[str, object]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            fail("catalog entry must be a mapping")
            continue
        component = entry.get("component")
        if not isinstance(component, str) or not component.startswith("platform-"):
            fail(f"catalog entry invalid component: {component!r}")
            continue
        if component in catalog_by_name:
            fail(f"catalog.yaml duplicate component: {component}")
        catalog_by_name[component] = entry

    registered = _discover_registered_components()

    # Gate #30: every registered platform-* → design-system folder
    for component in sorted(registered):
        folder = DS_ROOT / "components" / component
        if not folder.is_dir():
            fail(f"#30 missing design-system folder for {component}: {folder}")

    # Gate #31: five required files + manifest schema
    for component in sorted(catalog_by_name):
        folder = DS_ROOT / "components" / component
        if not folder.is_dir():
            continue
        for filename in REQUIRED_FILES:
            if not (folder / filename).is_file():
                fail(f"#31 {component}: missing {filename}")
        if not any((folder / name).is_file() for name in CONTRACT_SPEC_NAMES):
            fail(f"#31 {component}: missing contract.spec.ts/.js")
        manifest_path = folder / "manifest.yaml"
        if manifest_path.is_file():
            manifest_raw = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(manifest_raw, dict):
                fail(f"#31 {component}: manifest.yaml must be a mapping")
            else:
                _validate_manifest_schema(manifest_raw, schema, manifest_path)
                manifest_component = manifest_raw.get("component")
                if manifest_component != component:
                    fail(f"#31 {component}: manifest component mismatch ({manifest_component!r})")

    # Gate #32: catalog ↔ filesystem sync, no orphans
    components_dir = DS_ROOT / "components"
    if components_dir.is_dir():
        for child in sorted(p for p in components_dir.iterdir() if p.is_dir() and not p.name.startswith("_")):
            if child.name not in catalog_by_name:
                fail(f"#32 orphan design-system folder not in catalog.yaml: {child.name}")
            if child.name not in registered:
                fail(f"#32 orphan folder for unregistered component: {child.name}")

    for component in sorted(catalog_by_name):
        if component not in registered:
            fail(f"#32 catalog entry for unregistered component: {component}")

    # Gate #33: production → L1+L2 files present (not skipped-only)
    for component, entry in sorted(catalog_by_name.items()):
        status = entry.get("status")
        if status != "production":
            if status == "backlog" and "deadline" not in entry:
                fail(f"#33 {component}: backlog entry requires deadline")
            continue
        pw_path = DS_ROOT / "components" / component / "playwright.spec.py"
        if not pw_path.is_file():
            fail(f"#33 {component}: production requires playwright.spec.py")
            continue
        pw_text = pw_path.read_text(encoding="utf-8")
        if "@pytest.mark.skip" in pw_text and "backlog" in pw_text:
            fail(f"#33 {component}: production must not use backlog-skipped Playwright spec")

    if ERRORS:
        for err in ERRORS:
            print(f"check_ui_kit_docs: {err}", file=sys.stderr)
        return 1

    print(f"check_ui_kit_docs: OK ({len(catalog_by_name)} catalog entries, {len(registered)} registered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
