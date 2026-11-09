"""SEO-артефакты собранной документации: .md-зеркала, JSON-LD и lastmod в sitemap.

Запускается после ``zensical build`` и ``scripts.docs.postprocess`` (make doc,
Dockerfile docs-builder). Работает с ``build/documentation-{ru,en}`` (источники
сборки — ``shutil.copy2`` сохраняет mtime оригиналов) и ``documentation-dist``.

Для каждой страницы ``documentation-dist/**/index.html``:
- рядом кладётся ``index.md`` — исходный markdown без YAML-шапки (зеркало для LLM);
- в ``<head>`` добавляется ``<link rel="alternate" type="text/markdown">`` и
  ``<script type="application/ld+json">`` (TechArticle + BreadcrumbList);
- в ``sitemap.xml`` каждому ``<url>`` ставится ``<lastmod>`` по mtime источника.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from scripts.seo.seo_config import platform_name, seo_base_url

BASE_URL = seo_base_url()
DOC_BASE_RU = f"{BASE_URL}/documentation"
DOC_BASE_EN = f"{BASE_URL}/documentation/en"
PUBLISHER_ID = f"{BASE_URL}/#organization"
PLATFORM_NAME = platform_name()
OG_IMAGE_URL = f"{BASE_URL}/static/frontend/assets/images/main_img.png"

DIST_DIR = Path("documentation-dist")
RU_BUILD = Path("build/documentation-ru")
EN_BUILD = Path("build/documentation-en")

_FRONTMATTER_RE = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
# Жадный захват до ПОСЛЕДНЕГО разделителя: zensical добавляет « - Site Name»
# суффиксом; тайтл может сам содержать дефис («RAG-поиск - Linnex»).
_TITLE_RE = re.compile(r"<title>(.+)\s*[-–—]\s*", re.IGNORECASE)
_LASTMOD_RE = re.compile(r"(<loc>(.*?)</loc>)", re.DOTALL)
_URL_BLOCK_RE = re.compile(r"<url>\s*<loc>(.*?)</loc>", re.DOTALL)


def _strip_frontmatter(markdown_text: str) -> str:
    return _FRONTMATTER_RE.sub("", markdown_text, count=1).lstrip()


def _page_title(html: str) -> str:
    match = _TITLE_RE.search(html)
    return match.group(1).strip() if match else ""


def _lastmod(source_md: Path | None) -> str:
    """Дата контента: git-история оригинала или mtime подготовленного .md."""
    if source_md is not None:
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%cs", "--", _original_source(source_md)],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            stamp = out.stdout.strip()
            if stamp:
                return stamp
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            mtime = source_md.stat().st_mtime
        except OSError:
            return datetime.now(UTC).strftime("%Y-%m-%d")
        return datetime.fromtimestamp(mtime, UTC).strftime("%Y-%m-%d")
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _original_source(prepared_md: Path) -> str:
    """Путь оригинала для git: build/documentation-ru/x.md → docs/x.md."""
    parts = prepared_md.parts
    if len(parts) >= 3 and parts[0] == "build":
        return str(Path("docs") / Path(*parts[2:]))
    return str(prepared_md)


def _source_md_for(dist_html: Path, build_root: Path) -> Path | None:
    """dist/<path>/index.html → build/<path>.md или build/<path>/index.md."""
    rel = dist_html.parent.relative_to(DIST_DIR)
    if rel.parts and rel.parts[0] == "en":
        rel = Path(*rel.parts[1:])
    if str(rel) == ".":
        for candidate in (build_root / "index.md",):
            if candidate.is_file():
                return candidate
        return None
    for candidate in (build_root / f"{rel}.md", build_root / rel / "index.md"):
        if candidate.is_file():
            return candidate
    return None


def _md_mirror(dist_html: Path, source_md: Path | None) -> str | None:
    if source_md is None:
        return None
    mirror_path = dist_html.parent / "index.md"
    _ = mirror_path.write_text(
        _strip_frontmatter(source_md.read_text(encoding="utf-8")),
        encoding="utf-8",
    )
    return mirror_path.name


def _breadcrumb_items(page_url: str, locale: str, title: str) -> list[dict[str, object]]:
    rel = page_url.removeprefix(DOC_BASE_EN if locale == "en" else DOC_BASE_RU).strip("/")
    segments = [s for s in rel.split("/") if s]
    items: list[dict[str, object]] = [
        {
            "@type": "ListItem",
            "position": 1,
            "name": "Documentation" if locale == "en" else "Документация",
            "item": (DOC_BASE_EN if locale == "en" else DOC_BASE_RU) + "/",
        }
    ]
    current = DOC_BASE_EN if locale == "en" else DOC_BASE_RU
    for index, segment in enumerate(segments):
        current = f"{current}/{segment}"
        items.append(
            {
                "@type": "ListItem",
                "position": index + 2,
                "name": title if index == len(segments) - 1 else segment.replace("-", " ").title(),
                "item": f"{current}/",
            }
        )
    return items


def _ld_script(page_url: str, locale: str, title: str, lastmod: str, md_url: str | None) -> str:
    if not title:
        return ""
    article: dict[str, object] = {
        "@type": "TechArticle",
        "headline": title,
        "url": page_url,
        "inLanguage": locale,
        "image": OG_IMAGE_URL,
        "dateModified": lastmod,
        "publisher": {"@id": PUBLISHER_ID},
    }
    if md_url is not None:
        article["encoding"] = {
            "@type": "MediaObject",
            "contentUrl": md_url,
            "encodingFormat": "text/markdown",
        }
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            article,
            {
                "@type": "BreadcrumbList",
                "itemListElement": _breadcrumb_items(page_url, locale, title),
            },
            {
                "@type": "Organization",
                "@id": PUBLISHER_ID,
                "name": PLATFORM_NAME,
                "url": f"{BASE_URL}/",
            },
        ],
    }
    body = json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")
    return f'<script type="application/ld+json" id="docs-ld-json">{body}</script>'


def _inject_head(html: str, injection: str) -> str:
    match = re.search(r"</head>", html, re.IGNORECASE)
    if match is None:
        return html
    return html[: match.start()] + injection + "\n" + html[match.start():]


def _process_tree(dist_root: Path, build_root: Path, base: str, locale: str) -> int:
    processed = 0
    for html_path in sorted(dist_root.rglob("index.html")):
        rel_dir = html_path.parent.relative_to(DIST_DIR)
        if locale == "ru" and rel_dir.parts and rel_dir.parts[0] == "en":
            continue
        page_url = f"{base}/" if str(rel_dir) in (".", "en") else f"{base}/{'/'.join(rel_dir.parts[1:] if rel_dir.parts[0] == 'en' else rel_dir.parts)}/"
        source_md = _source_md_for(html_path, build_root)
        md_url: str | None = None
        if _md_mirror(html_path, source_md) is not None:
            md_url = f"{page_url}index.md"
        html = html_path.read_text(encoding="utf-8")
        if 'id="docs-ld-json"' in html or 'type="text/markdown"' in html:
            continue
        injections: list[str] = []
        if md_url is not None:
            injections.append(f'<link rel="alternate" type="text/markdown" href="{md_url}">')
        ld = _ld_script(page_url, locale, _page_title(html), _lastmod(source_md), md_url)
        if ld:
            injections.append(ld)
        if not injections:
            continue
        _ = html_path.write_text(_inject_head(html, "\n".join(injections)), encoding="utf-8")
        processed += 1
    return processed


def _patch_sitemap(sitemap_path: Path, build_root: Path, base: str) -> int:
    """lastmod в zensical-sitemap по mtime соответствующего .md источника."""
    if not sitemap_path.is_file():
        return 0
    xml = sitemap_path.read_text(encoding="utf-8")
    patched = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal patched
        loc = match.group(1)
        rel = loc.removeprefix(base).strip("/")
        for candidate in (build_root / f"{rel}.md", build_root / rel / "index.md", build_root / "index.md" if rel == "" else build_root / "__none__"):
            if candidate.is_file():
                patched += 1
                return f"<url>\n        <loc>{loc}</loc>\n        <lastmod>{_lastmod(candidate)}</lastmod>"
        return match.group(0)

    updated = _URL_BLOCK_RE.sub(_replace, xml)
    if updated != xml:
        _ = sitemap_path.write_text(updated, encoding="utf-8")
    return patched


def main() -> None:
    if not DIST_DIR.is_dir():
        print("docs seo_postbuild: documentation-dist отсутствует, пропуск")
        return
    processed = _process_tree(DIST_DIR, RU_BUILD, DOC_BASE_RU, "ru")
    en_dist = DIST_DIR / "en"
    if en_dist.is_dir():
        processed += _process_tree(en_dist, EN_BUILD, DOC_BASE_EN, "en")
    patched = _patch_sitemap(DIST_DIR / "sitemap.xml", RU_BUILD, DOC_BASE_RU)
    patched += _patch_sitemap(DIST_DIR / "en" / "sitemap.xml", EN_BUILD, DOC_BASE_EN)
    print(f"docs seo_postbuild: {processed} страниц (md+ld), {patched} lastmod в sitemap")


if __name__ == "__main__":
    main()
