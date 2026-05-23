"""Post-process built documentation HTML.

Zensical falls back to folder slugs for some intermediate navigation groups.
Keep URLs stable (`/scenarios/crm/`) while exposing the product brand as
NetWorkle in generated navigation.
"""

from __future__ import annotations

from pathlib import Path

REPLACEMENTS_RU = {
    "Crm settings hub": "NetWorkle: хаб настроек",
    "Crm shell": "NetWorkle: оболочка записной книжки",
    "Crm": "NetWorkle",
}

REPLACEMENTS_EN = {
    "Crm settings hub": "NetWorkle: settings hub",
    "Crm shell": "NetWorkle: notebook shell",
    "Crm": "NetWorkle",
}


def _postprocess_html(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    updated = text
    replacements = REPLACEMENTS_EN if "en" in path.parts else REPLACEMENTS_RU
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    root = Path("documentation-dist")
    if not root.is_dir():
        return
    changed = sum(1 for path in root.rglob("*.html") if _postprocess_html(path))
    print(f"docs postprocess: updated {changed} html files")


if __name__ == "__main__":
    main()
