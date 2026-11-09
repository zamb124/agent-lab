"""Расположение seo-dist артефактов блога и статических снапшотов."""

from __future__ import annotations

from pathlib import Path

from apps.frontend.config import get_frontend_settings
from apps.frontend.seo.pages import SeoLocale
from core.logging import get_logger
from core.types import JsonObject, JsonValue, parse_json_array

logger = get_logger(__name__)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def seo_dist_root() -> Path:
    """Каталог статических SEO-артефактов (блог, статические страницы)."""
    return get_frontend_settings().seo_dist_dir


def blog_post_html_path(slug: str, locale: SeoLocale) -> Path:
    """Файл статической страницы поста: ``seo-dist/blog/<slug>/index.html`` (ru),
    ``seo-dist/en/blog/<slug>/index.html`` (en)."""
    root = seo_dist_root() / "blog" if locale == "ru" else seo_dist_root() / "en" / "blog"
    return root / slug / "index.html"


def blog_feed_path() -> Path:
    return seo_dist_root() / "blog" / "feed.xml"


def blog_index_path() -> Path:
    return seo_dist_root() / "blog" / "index.json"


def blog_body_path(slug: str, locale: SeoLocale) -> Path:
    """Фрагмент тела поста для API: ``seo-dist/(en/)blog/<slug>/body.html``."""
    root = seo_dist_root() / "blog" if locale == "ru" else seo_dist_root() / "en" / "blog"
    return root / slug / "body.html"


# Проблема blog-артефактов логируется один раз на процесс: файлы меняются
# только с деплоем, а потребители (sitemap, public API) дергаются краулерами.
_blog_problem_logged = False


def _log_problem(event: str, **fields: JsonValue) -> None:
    global _blog_problem_logged
    if _blog_problem_logged:
        return
    _blog_problem_logged = True
    logger.warning(event, **fields)


def read_blog_index() -> list[JsonObject]:
    """Карточки постов из ``seo-dist/blog/index.json``.

    Файл отсутствует или битый → ``[]`` + alertable-событие
    ``seo.blog_index_missing`` / ``seo.blog_index_invalid`` (Grafana
    ``seo-blog-index-missing``): потребители отдают пустой список, а не 500.
    """
    index_path = blog_index_path()
    if not index_path.is_file():
        _log_problem("seo.blog_index_missing", path=str(index_path))
        return []
    try:
        raw_items = parse_json_array(index_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _log_problem("seo.blog_index_invalid", path=str(index_path), error=str(exc))
        return []
    items: list[JsonObject] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        if not item.get("slug") or not item.get("updated"):
            _log_problem("seo.blog_index_invalid", path=str(index_path), item=str(item))
            continue
        items.append(item)
    return items


def read_blog_body(slug: str) -> str | None:
    """Тело поста (ru-фрагмент); ``None`` — файла нет (alertable-событие)."""
    body_path = blog_body_path(slug, "ru")
    if not body_path.is_file():
        _log_problem("seo.blog_body_missing", path=str(body_path))
        return None
    return body_path.read_text(encoding="utf-8")
