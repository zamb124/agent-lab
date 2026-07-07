#!/usr/bin/env python3
"""Generate UI Kit hub pages and sync component README stubs into docs/scenarios."""

from __future__ import annotations

import textwrap
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DS_ROOT = ROOT / "tests" / "ui" / "design-system"
DOCS_HUB = ROOT / "docs" / "scenarios" / "platform" / "ui-kit"


def _load_catalog() -> list[dict[str, str]]:
    raw = yaml.safe_load((DS_ROOT / "catalog.yaml").read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("catalog.yaml root must be a mapping")
    entries = raw.get("components")
    if not isinstance(entries, list):
        raise ValueError("catalog.yaml components must be a list")
    out: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("catalog entry must be a mapping")
        component = entry.get("component")
        status = entry.get("status")
        tier = entry.get("tier")
        doc_slug = entry.get("doc_slug")
        if not all(isinstance(v, str) and v for v in (component, status, tier, doc_slug)):
            raise ValueError(f"invalid catalog entry: {entry!r}")
        out.append(
            {
                "component": component,
                "status": status,
                "tier": tier,
                "doc_slug": doc_slug,
            }
        )
    return out


def _write_hub(*, lang: str) -> None:
    entries = _load_catalog()
    DOCS_HUB.mkdir(parents=True, exist_ok=True)
    if lang == "en":
        title = "Platform UI Kit"
        intro = "Catalog of core `platform-*` components with contract tests, Playwright scenarios, and playground previews."
        status_label = "Status"
        tier_label = "Tier"
        lines = [f"# {title}", "", intro, "", "| Component | Tier | Status |", "| --- | --- | --- |"]
    else:
        title = "UI Kit платформы"
        intro = "Каталог core-компонентов `platform-*`: contract-тесты, Playwright-сценарии и playground preview."
        status_label = "Статус"
        tier_label = "Tier"
        lines = [f"# {title}", "", intro, "", "| Компонент | Tier | Статус |", "| --- | --- | --- |"]

    for entry in sorted(entries, key=lambda item: item["component"]):
        slug = entry["doc_slug"]
        link = f"[{entry['component']}](../{slug}/)"
        lines.append(f"| {link} | {entry['tier']} | {entry['status']} |")

    lines.extend(
        [
            "",
            "## Playground",
            "",
            "```text",
            "/frontend/design-system/preview?component=platform-button&variant=primary",
            "```",
            "",
            "## Tests",
            "",
            "```bash",
            "make ui",
            "make ui-doc",
            "```",
            "",
        ]
    )
    _ = status_label, tier_label
    filename = "README.en.md" if lang == "en" else "README.md"
    (DOCS_HUB / filename).write_text("\n".join(lines), encoding="utf-8")


def _sync_component_readmes() -> None:
    for entry in _load_catalog():
        slug = entry["doc_slug"]
        src = DS_ROOT / "components" / entry["component"]
        dst = DOCS_HUB / slug
        dst.mkdir(parents=True, exist_ok=True)
        for name in ("README.md", "README.en.md"):
            source = src / name
            if source.is_file():
                (dst / name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")


def main() -> None:
    _write_hub(lang="ru")
    _write_hub(lang="en")
    _sync_component_readmes()
    print(f"generate_ui_kit_docs: hub at {DOCS_HUB}")


if __name__ == "__main__":
    main()
