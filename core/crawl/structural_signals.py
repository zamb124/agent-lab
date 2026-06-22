"""Layer-0 HTML metadata extraction for crawl fetch (no LLM)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import cast
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from core.crawl.models import CrawlContentType, CrawlStructuralSignals
from core.types import JsonObject, JsonValue, require_json_object

_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_SCHEMA_ORG_TYPES: dict[str, CrawlContentType] = {
    "article": "article",
    "newsarticle": "news",
    "blogposting": "blog",
    "webpage": "reference",
    "aboutpage": "reference",
    "contactpage": "reference",
    "searchresultspage": "reference",
    "collectionpage": "catalog",
    "itempage": "product",
    "product": "product",
    "faqpage": "faq",
    "qapage": "faq",
    "howto": "tutorial",
    "techarticle": "documentation",
    "softwareapplication": "tool",
    "webapplication": "tool",
    "mobileapplication": "tool",
    "scholarlyarticle": "research",
    "report": "report",
    "review": "review",
    "recipe": "recipe",
    "event": "event",
    "legislation": "legal",
    "legalservice": "legal",
    "discussionforumposting": "forum",
    "socialmediaposting": "blog",
    "profilepage": "reference",
    "checkoutpage": "catalog",
    "offer": "product",
    "creativework": "article",
    "mediaobject": "reference",
    "videoobject": "reference",
    "audioobject": "reference",
    "dataset": "research",
    "course": "tutorial",
    "learningresource": "tutorial",
    "specialannouncement": "press_release",
    "advertisercontentarticle": "article",
    "liveblogposting": "news",
    "apartment": "product",
    "house": "product",
    "singlefamilyresidence": "product",
    "vehicle": "product",
    "car": "product",
}
_OG_TYPE_MAP: dict[str, CrawlContentType] = {
    "article": "article",
    "website": "landing",
    "product": "product",
    "profile": "reference",
    "video.other": "reference",
    "video.movie": "reference",
    "video.episode": "reference",
    "music.song": "reference",
    "music.album": "reference",
    "book": "reference",
    "blog": "blog",
}


@dataclass
class JsonLdSignals:
    title: str | None = None
    date_published: date | None = None
    date_modified: date | None = None
    author: str | None = None
    publisher: str | None = None
    content_type_hint: CrawlContentType | None = None
    category_hints: list[str] = field(default_factory=list)
    topic_hints: list[str] = field(default_factory=list)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def _tag_attribute_text(tag: Tag, attribute: str) -> str | None:
    raw = tag.get(attribute)
    if raw is None:
        return None
    if isinstance(raw, list):
        for item in raw:
            normalized = _normalize_text(item)
            if normalized is not None:
                return normalized
        return None
    return _normalize_text(raw)


def _parse_iso_date(value: str | None) -> date | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.date()
    except ValueError:
        match = _ISO_DATE_RE.match(normalized)
        if match is None:
            return None
        year = int(match.group(1))
        month = int(match.group(2))
        day = int(match.group(3))
        return date(year, month, day)


def _meta_content(soup: BeautifulSoup, *, prop: str | None = None, name: str | None = None) -> str | None:
    if prop is not None:
        tag = soup.find("meta", attrs={"property": prop})
        if isinstance(tag, Tag):
            return _tag_attribute_text(tag, "content")
    if name is not None:
        tag = soup.find("meta", attrs={"name": name})
        if isinstance(tag, Tag):
            return _tag_attribute_text(tag, "content")
    return None


def _append_json_ld_object(objects: list[JsonObject], value: JsonValue) -> None:
    if isinstance(value, dict):
        objects.append(require_json_object(cast(object, value), "json-ld"))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                objects.append(require_json_object(cast(object, item), "json-ld"))


def _first_json_ld_objects(soup: BeautifulSoup) -> list[JsonObject]:
    objects: list[JsonObject] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if not isinstance(script, Tag):
            continue
        raw = script.string
        if raw is None or not raw.strip():
            continue
        try:
            payload = cast(JsonValue, json.loads(raw))
        except json.JSONDecodeError:
            continue
        _append_json_ld_object(objects, payload)
    return objects


def _json_ld_type(raw_type: JsonValue | None) -> str | None:
    if isinstance(raw_type, str):
        return raw_type.split("/")[-1].lower()
    if isinstance(raw_type, list):
        for item in raw_type:
            if isinstance(item, str):
                return item.split("/")[-1].lower()
    return None


def _json_ld_string_field(node: JsonObject, key: str) -> str | None:
    value = node.get(key)
    if isinstance(value, str):
        return _normalize_text(value)
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str):
            return _normalize_text(name)
    return None


def _map_content_type_hint(raw: str | None) -> CrawlContentType | None:
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if not normalized:
        return None
    schema_key = normalized.split("/")[-1].replace(" ", "").replace("-", "")
    if schema_key in _SCHEMA_ORG_TYPES:
        return _SCHEMA_ORG_TYPES[schema_key]
    if normalized in _OG_TYPE_MAP:
        return _OG_TYPE_MAP[normalized]
    return None


def _append_unique_token(tokens: list[str], raw: str | None) -> None:
    token = _normalize_text(raw)
    if token is not None and token not in tokens:
        tokens.append(token)


def _collect_json_ld_signals(objects: list[JsonObject]) -> JsonLdSignals:
    signals = JsonLdSignals()

    for node in objects:
        node_type = _json_ld_type(node.get("@type"))
        if signals.content_type_hint is None and node_type is not None:
            signals.content_type_hint = _map_content_type_hint(node_type)

        if signals.title is None:
            signals.title = _json_ld_string_field(node, "headline")
            if signals.title is None:
                signals.title = _json_ld_string_field(node, "name")

        if signals.date_published is None:
            signals.date_published = _parse_iso_date(_json_ld_string_field(node, "datePublished"))
        if signals.date_modified is None:
            signals.date_modified = _parse_iso_date(_json_ld_string_field(node, "dateModified"))

        if signals.author is None:
            signals.author = _json_ld_string_field(node, "author")
        if signals.publisher is None:
            signals.publisher = _json_ld_string_field(node, "publisher")

        section = _json_ld_string_field(node, "articleSection")
        if section is not None:
            _append_unique_token(signals.category_hints, section)

        keywords = node.get("keywords")
        if isinstance(keywords, str):
            for part in re.split(r"[,;]", keywords):
                _append_unique_token(signals.topic_hints, part)
        elif isinstance(keywords, list):
            for item in keywords:
                if isinstance(item, str):
                    _append_unique_token(signals.topic_hints, item)

    return signals


def _first_time_datetime(soup: BeautifulSoup) -> date | None:
    for time_tag in soup.find_all("time"):
        if not isinstance(time_tag, Tag):
            continue
        parsed = _parse_iso_date(_tag_attribute_text(time_tag, "datetime"))
        if parsed is not None:
            return parsed
    return None


def _breadcrumb_categories(soup: BeautifulSoup) -> list[str]:
    crumbs: list[str] = []
    for nav in soup.find_all(["nav", "ol", "ul"], class_=re.compile(r"breadcrumb", re.I)):
        if not isinstance(nav, Tag):
            continue
        for anchor in nav.find_all("a"):
            if not isinstance(anchor, Tag):
                continue
            label = _normalize_text(anchor.get_text())
            if label is not None and label not in crumbs:
                crumbs.append(label)
    return crumbs[:5]


def _resolve_absolute_url(page_url: str, raw_url: str | None) -> str | None:
    normalized = _normalize_text(raw_url)
    if normalized is None:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme in {"http", "https"}:
        return normalized
    if not page_url.strip():
        return None
    return urljoin(page_url.strip(), normalized)


def extract_structural_signals_from_html(html: str, *, page_url: str = "") -> CrawlStructuralSignals:
    soup = BeautifulSoup(html, "html.parser")
    json_ld = _collect_json_ld_signals(_first_json_ld_objects(soup))

    og_title = _meta_content(soup, prop="og:title")
    og_type = _meta_content(soup, prop="og:type")
    title_tag = soup.find("title")
    html_title: str | None = None
    if isinstance(title_tag, Tag):
        html_title = _normalize_text(title_tag.get_text())

    title = json_ld.title
    if title is None:
        title = og_title
    if title is None:
        title = html_title

    date_published = json_ld.date_published
    if date_published is None:
        date_published = _parse_iso_date(_meta_content(soup, prop="article:published_time"))
    if date_published is None:
        date_published = _first_time_datetime(soup)

    date_modified = json_ld.date_modified
    if date_modified is None:
        date_modified = _parse_iso_date(_meta_content(soup, prop="article:modified_time"))

    author = json_ld.author
    if author is None:
        author = _meta_content(soup, name="author")

    publisher = json_ld.publisher
    if publisher is None:
        publisher = _meta_content(soup, prop="og:site_name")

    html_lang: str | None = None
    html_node = soup.find("html")
    if isinstance(html_node, Tag):
        lang_attr = _tag_attribute_text(html_node, "lang")
        if lang_attr is not None:
            lang_token = lang_attr.split("-")[0].lower()
            if len(lang_token) >= 2:
                html_lang = lang_token

    content_type_hint = json_ld.content_type_hint
    if content_type_hint is None:
        content_type_hint = _map_content_type_hint(og_type)

    category_hints = list(json_ld.category_hints)
    section = _meta_content(soup, prop="article:section")
    if section is not None and section not in category_hints:
        category_hints.append(section)
    for crumb in _breadcrumb_categories(soup):
        if crumb not in category_hints:
            category_hints.append(crumb)

    topic_hints = list(json_ld.topic_hints)
    keywords = _meta_content(soup, name="keywords")
    if keywords is not None:
        for part in re.split(r"[,;]", keywords):
            _append_unique_token(topic_hints, part)
    for meta_tag in soup.find_all("meta", attrs={"property": "article:tag"}):
        if not isinstance(meta_tag, Tag):
            continue
        content = _tag_attribute_text(meta_tag, "content")
        if content is not None and content not in topic_hints:
            topic_hints.append(content)

    og_image_url = _resolve_absolute_url(page_url, _meta_content(soup, prop="og:image"))

    return CrawlStructuralSignals(
        title=title,
        date_published=date_published,
        date_modified=date_modified,
        author=author,
        publisher=publisher,
        og_image_url=og_image_url,
        language=html_lang,
        content_type_hint=content_type_hint,
        category_hints=category_hints[:10],
        topic_hints=topic_hints[:15],
    )
