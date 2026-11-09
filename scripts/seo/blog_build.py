"""Сборка статических страниц блога: ``blog/*.md`` → ``seo-dist/``.

Источник — ``blog/<slug>.md`` (ru) и ``blog/<slug>.en.md`` (en) с YAML-шапкой
(``title``, ``summary``, ``date``, ``updated``, ``author``, ``tags``, ``draft``).
Результат:

- ``seo-dist/blog/<slug>/index.html`` — полная индексируемая страница поста (ru);
- ``seo-dist/en/blog/<slug>/index.html`` — английская версия (если есть ``.en.md``);
- ``seo-dist/blog/<slug>/body.html`` / ``seo-dist/en/blog/<slug>/body.html`` —
  фрагмент тела для ``/api/public/blog/post``;
- ``seo-dist/blog/index.json`` — каталог карточек (sitemap + список API);
- ``seo-dist/blog/feed.xml`` — RSS 2.0.

Запуск: ``python -m scripts.seo.blog_build`` (make target ``seo-build``, часть ``ui-build``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path

import markdown
import yaml

from scripts.seo.seo_config import platform_name, seo_base_url

REPO_ROOT = Path(__file__).resolve().parents[2]
BLOG_SOURCE_DIR = REPO_ROOT / "blog"
SEO_DIST_DIR = REPO_ROOT / "seo-dist"
SHELL_TEMPLATE_PATH = Path(__file__).resolve().parent / "blog_shell.html"

SEO_BASE_URL = seo_base_url()
PLATFORM_NAME = platform_name()
OG_IMAGE_URL = f"{SEO_BASE_URL}/static/frontend/assets/images/main_img.png"
_LOGO_URL = f"{SEO_BASE_URL}/static/core/assets/service_logos/frontend_logo.svg"

_MD_EXTENSIONS = ["fenced_code", "tables", "attr_list", "sane_lists"]
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_SLUG_RE = re.compile(r"\A[a-z0-9][a-z0-9-]*\Z")

_MONTHS_RU = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_MONTHS_EN = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


@dataclass(frozen=True)
class PostSource:
    slug: str
    title: str
    summary: str
    date: str
    updated: str
    author: str
    tags: tuple[str, ...]
    draft: bool
    body_html: str


def _str_dict(value: object, field: str) -> dict[str, object]:
    """mapping из YAML-шапки с нормализацией ключей — isinstance(dict) дал бы Unknown."""
    if not isinstance(value, dict):
        raise ValueError(f"YAML-шапка не mapping: {field}")
    return {str(k): v for k, v in value.items()}


def _parse_post(path: Path, slug: str) -> PostSource:
    raw = path.read_text(encoding="utf-8")
    match = _FRONTMATTER_RE.match(raw)
    if match is None:
        raise ValueError(f"{path}: нет YAML-шапки (--- ... ---)")
    meta = _str_dict(yaml.safe_load(match.group(1)), str(path))
    body = raw[match.end() :]
    title = str(meta.get("title") or "").strip()
    summary = str(meta.get("summary") or "").strip()
    if not title or not summary:
        raise ValueError(f"{path}: в шапке обязательны title и summary")
    date = str(meta.get("date") or "").strip()
    if not date:
        raise ValueError(f"{path}: в шапке обязателен date")
    updated = str(meta.get("updated") or date).strip()
    body_html = markdown.markdown(body, extensions=_MD_EXTENSIONS).strip()
    if not body_html:
        raise ValueError(f"{path}: пустое тело после frontmatter")
    tags_raw = meta.get("tags") or []
    tags = tuple(str(t) for t in tags_raw) if isinstance(tags_raw, list) else ()
    return PostSource(
        slug=slug,
        title=title,
        summary=summary,
        date=date,
        updated=updated,
        author=str(meta.get("author") or PLATFORM_NAME).strip(),
        tags=tags,
        draft=bool(meta.get("draft") or False),
        body_html=body_html,
    )


def _human_date(iso: str, locale: str) -> str:
    parsed = datetime.fromisoformat(iso)
    months = _MONTHS_EN if locale == "en" else _MONTHS_RU
    return f"{parsed.day} {months[parsed.month - 1]} {parsed.year}"


def _ld_json(post: PostSource, *, locale: str, url_ru: str, url_en: str) -> str:
    canonical = url_en if locale == "en" else url_ru
    platform = PLATFORM_NAME
    graph = {
        "@context": "https://schema.org",
        "@graph": [
            {
                "@type": "BlogPosting",
                "headline": post.title.replace("{platformName}", platform),
                "description": post.summary.replace("{platformName}", platform),
                "datePublished": post.date,
                "dateModified": post.updated,
                "inLanguage": locale,
                "image": OG_IMAGE_URL,
                "mainEntityOfPage": {"@type": "WebPage", "@id": canonical},
                "author": {"@type": "Organization", "name": platform},
                "publisher": {
                    "@type": "Organization",
                    "@id": f"{SEO_BASE_URL}/#organization",
                    "name": platform,
                    "logo": _LOGO_URL,
                },
            },
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "name": "Home" if locale == "en" else "Главная",
                        "item": f"{SEO_BASE_URL}/{'en' if locale == 'en' else ''}".rstrip("/")
                        + "/",
                    },
                    {
                        "@type": "ListItem",
                        "position": 2,
                        "name": "Blog" if locale == "en" else "Блог",
                        "item": f"{SEO_BASE_URL}/{'en/blog' if locale == 'en' else 'blog'}",
                    },
                    {
                        "@type": "ListItem",
                        "position": 3,
                        "name": post.title.replace("{platformName}", platform),
                        "item": canonical,
                    },
                ],
            },
        ],
    }
    return json.dumps(graph, ensure_ascii=False).replace("</", "<\\/")


def _render_shell(post: PostSource, *, locale: str, has_en: bool) -> str:
    template = SHELL_TEMPLATE_PATH.read_text(encoding="utf-8")
    is_en = locale == "en"
    url_ru = f"{SEO_BASE_URL}/blog/{post.slug}"
    url_en = f"{SEO_BASE_URL}/en/blog/{post.slug}"
    canonical = url_en if is_en else url_ru
    prefix = "en/" if is_en else ""
    platform = PLATFORM_NAME

    title = escape(post.title.replace("{platformName}", platform))
    summary = escape(post.summary.replace("{platformName}", platform))
    body = post.body_html.replace("{platformName}", platform)
    author = escape(post.author.replace("{platformName}", platform))

    tokens = {
        "LANG": "en" if is_en else "ru",
        "TITLE": title,
        "DESCRIPTION": summary,
        "SUMMARY": summary,
        "CANONICAL": canonical,
        # en-alternate и x-default — только когда en-страница реально существует.
        "HREFLANG_BLOCK": (
            "\n".join(
                (
                    f'    <link rel="alternate" hreflang="ru" href="{url_ru}">',
                    f'    <link rel="alternate" hreflang="en" href="{url_en}">',
                    f'    <link rel="alternate" hreflang="x-default" href="{url_ru}">',
                )
            )
            if has_en
            else f'    <link rel="alternate" hreflang="ru" href="{url_ru}">'
        ),
        "BASE_URL": SEO_BASE_URL,
        "PLATFORM_NAME": platform,
        "OG_LOCALE": "en_US" if is_en else "ru_RU",
        "OG_IMAGE": OG_IMAGE_URL,
        "DATE": post.date,
        "UPDATED": post.updated,
        "DATE_HUMAN": _human_date(post.date, locale),
        "AUTHOR": author,
        "BODY": body,
        "LD_JSON": _ld_json(post, locale=locale, url_ru=url_ru, url_en=url_en),
        "HOME_URL": f"{SEO_BASE_URL}/{'en' if is_en else ''}".rstrip("/") + "/",
        "BLOG_URL": f"{SEO_BASE_URL}/{prefix}blog",
        "PRODUCTS_URL": f"{SEO_BASE_URL}/{prefix}products/agents",
        "DOC_PREFIX": "en/" if is_en else "",
        "YEAR": str(datetime.now(UTC).year),
        "NAV_HOME": "Home" if is_en else "Главная",
        "NAV_DOCS": "Documentation" if is_en else "Документация",
        "NAV_PRODUCTS": "Products" if is_en else "Продукты",
        "NAV_BLOG": "Blog" if is_en else "Блог",
        "FOOTER_POLICY": "Privacy policy" if is_en else "Политика конфиденциальности",
        "CTA_TITLE": (
            f"Try {platform} for your business" if is_en else f"Попробуйте {platform} для бизнеса"
        ),
        "CTA_TEXT": (
            "AI agents, knowledge base, NetWorkle graph, chat and documents — in one platform."
            if is_en
            else "AI-агенты, база знаний, граф NetWorkle, чат и документы — в одной платформе."
        ),
        "CTA_BUTTON": "Start for free" if is_en else "Начать бесплатно",
    }
    html = template
    for key, value in tokens.items():
        html = html.replace(f"%%{key}%%", value)
    unresolved = re.findall(r"%%[A-Z_]+%", html)
    if unresolved:
        raise ValueError(f"blog shell: неразрешённые плейсхолдеры {unresolved}")
    return html


def _feed_xml(posts: list[tuple[PostSource, PostSource | None]]) -> str:
    items: list[str] = []
    for ru, _en in sorted(posts, key=lambda p: p[0].date, reverse=True)[:20]:
        pub = format_datetime(datetime.fromisoformat(ru.date).replace(tzinfo=UTC))
        title = escape(ru.title.replace("{platformName}", PLATFORM_NAME))
        summary = escape(ru.summary.replace("{platformName}", PLATFORM_NAME))
        items.append(
            "  <item>\n"
            + f"    <title>{title}</title>\n"
            + f"    <link>{SEO_BASE_URL}/blog/{ru.slug}</link>\n"
            + f'    <guid isPermaLink="true">{SEO_BASE_URL}/blog/{ru.slug}</guid>\n'
            + f"    <description>{summary}</description>\n"
            + f"    <pubDate>{pub}</pubDate>\n"
            + "  </item>"
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        + '<rss version="2.0">\n<channel>\n'
        + f"  <title>{PLATFORM_NAME} Blog</title>\n"
        + f"  <link>{SEO_BASE_URL}/blog</link>\n"
        + f"  <description>Статьи о платформе {PLATFORM_NAME}: AI-агенты, RAG, автоматизация.</description>\n"
        + "  <language>ru</language>\n" + "\n".join(items) + "\n</channel>\n</rss>\n"
    )


def build() -> list[dict[str, object]]:
    if not BLOG_SOURCE_DIR.is_dir():
        raise FileNotFoundError(f"нет каталога источников блога: {BLOG_SOURCE_DIR}")
    index: list[dict[str, object]] = []
    posts: list[tuple[PostSource, PostSource | None]] = []
    for path in sorted(BLOG_SOURCE_DIR.glob("*.md")):
        if path.name.endswith(".en.md"):
            continue
        slug = path.stem
        if not _SLUG_RE.match(slug):
            raise ValueError(f"{path}: slug '{slug}' не [a-z0-9-]+")
        ru = _parse_post(path, slug)
        if ru.draft:
            continue
        en_path = BLOG_SOURCE_DIR / f"{slug}.en.md"
        en = _parse_post(en_path, slug) if en_path.is_file() else None
        posts.append((ru, en))

        ru_dir = SEO_DIST_DIR / "blog" / slug
        ru_dir.mkdir(parents=True, exist_ok=True)
        _ = (ru_dir / "index.html").write_text(
            _render_shell(ru, locale="ru", has_en=en is not None), encoding="utf-8"
        )
        _ = (ru_dir / "body.html").write_text(ru.body_html, encoding="utf-8")

        has_en = en is not None
        if en is not None:
            en_dir = SEO_DIST_DIR / "en" / "blog" / slug
            en_dir.mkdir(parents=True, exist_ok=True)
            _ = (en_dir / "index.html").write_text(
                _render_shell(en, locale="en", has_en=True), encoding="utf-8"
            )
            _ = (en_dir / "body.html").write_text(en.body_html, encoding="utf-8")

        index.append(
            {
                "slug": slug,
                "title_ru": ru.title,
                "title_en": en.title if en is not None else ru.title,
                "summary_ru": ru.summary,
                "summary_en": en.summary if en is not None else ru.summary,
                "date": ru.date,
                "updated": ru.updated,
                "has_en": has_en,
                "tags": list(ru.tags),
            }
        )

    index.sort(key=lambda item: str(item["date"]), reverse=True)
    blog_dir = SEO_DIST_DIR / "blog"
    blog_dir.mkdir(parents=True, exist_ok=True)
    _ = (blog_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _ = (blog_dir / "feed.xml").write_text(_feed_xml(posts), encoding="utf-8")
    return index


def main() -> int:
    index = build()
    print(f"blog_build: {len(index)} постов → {SEO_DIST_DIR.relative_to(REPO_ROOT)}/blog/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
