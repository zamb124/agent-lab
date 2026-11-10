"""Post-process built documentation files.

Zensical falls back to folder slugs for some intermediate navigation groups.
Keep URLs stable (`/scenarios/crm/`) while exposing the product brand as
NetWorkle and product terms in generated navigation/search metadata.

Service hubs (`/scenarios/<service>/`) additionally get the platform's real
service SVG logo injected into the left sidebar navigation link, matching the
icon used on the "Инструкции" service cards and in the SPA launcher.
"""

from __future__ import annotations

import posixpath
import re
from pathlib import Path

from scripts.docs.prepare import SERVICE_LOGO_FILES

REPLACEMENTS_RU = {
    "Api": "API",
    "Guides": "Руководства",
    "Crm settings hub": "NetWorkle: хаб настроек",
    "Crm shell": "NetWorkle: оболочка записной книжки",
    "Crm": "NetWorkle",
    "Scenarios": "Инструкции",
}

REPLACEMENTS_EN = {
    "Api": "API",
    "Crm settings hub": "NetWorkle: settings hub",
    "Crm shell": "NetWorkle: notebook shell",
    "Crm": "NetWorkle",
    "Scenarios": "Instructions",
}

_DIST_ROOT = Path("documentation-dist")
_EN_ROOT = _DIST_ROOT / "en"

# Ссылка сайдбара: <a href="..." class="md-nav__link[ ...]"> <span class="md-ellipsis">
_NAV_LINK_RE = re.compile(
    r'<a href="(?P<href>[^"]+)" class="md-nav__link(?P<cls>[^"]*)"\s*>'
    r'(?P<body>\s*<span class="md-ellipsis">)'
)
_SERVICE_HUB_RE = re.compile(r"^scenarios/(?P<service>[a-z0-9_-]+)/?$")


def _site_root_for(path: Path) -> Path | None:
    """Корень собранного сайта для html-файла (RU-дерево или en-поддерево)."""
    try:
        path.relative_to(_EN_ROOT)
    except ValueError:
        pass
    else:
        return _EN_ROOT
    try:
        path.relative_to(_DIST_ROOT)
    except ValueError:
        return None
    return _DIST_ROOT


def _service_for_href(href: str, url_dir: str) -> str | None:
    """Имя сервиса, если ссылка ведёт ровно на хаб `scenarios/<service>/`."""
    path = href.split("#", 1)[0].split("?", 1)[0]
    if not path:
        return None
    resolved = posixpath.normpath(posixpath.join(url_dir, path))
    match = _SERVICE_HUB_RE.match(resolved + "/")
    if match is None:
        return None
    return match.group("service")


def _inject_service_nav_icons(text: str, path: Path, site_root: Path) -> str:
    url_dir = path.parent.relative_to(site_root).as_posix()
    if url_dir == ".":
        url_dir = ""

    def _replace(match: re.Match[str]) -> str:
        service = _service_for_href(match.group("href"), url_dir)
        if service is None:
            return match.group(0)
        logo = SERVICE_LOGO_FILES.get(service)
        if logo is None:
            return match.group(0)
        icon_rel = posixpath.relpath(
            f"assets/service_logos/{logo}", url_dir or "."
        )
        return (
            f"{match.group(0)}"
            f'<img class="docs-nav-icon" src="{icon_rel}" alt="" '
            f'aria-hidden="true" loading="lazy">'
        )

    return _NAV_LINK_RE.sub(_replace, text)


def _postprocess_html(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    updated = text
    replacements = REPLACEMENTS_EN if "en" in path.parts else REPLACEMENTS_RU
    for old, new in replacements.items():
        updated = updated.replace(old, new)
    site_root = _site_root_for(path)
    if site_root is not None and path.suffix == ".html":
        updated = _inject_service_nav_icons(updated, path, site_root)
    if updated == text:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def main() -> None:
    if not _DIST_ROOT.is_dir():
        return
    paths = [*_DIST_ROOT.rglob("*.html"), *_DIST_ROOT.rglob("search.json")]
    changed = sum(1 for path in paths if _postprocess_html(path))
    print(f"docs postprocess: updated {changed} files")


if __name__ == "__main__":
    main()
