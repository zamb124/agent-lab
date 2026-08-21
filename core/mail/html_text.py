"""Видимый текст HTML-письма для snippet и RAG. Не рендер."""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Final, final, override

_SKIP_TAGS: Final[frozenset[str]] = frozenset(
    {"script", "style", "noscript", "head", "title", "iframe", "object", "embed"}
)
_HTML_PREFIXES: Final[tuple[str, ...]] = (
    "<!doctype",
    "<html",
    "<head",
    "<body",
    "<div",
    "<table",
    "<p",
    "<span",
    "<meta",
)


@final
class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._skip_depth: int = 0

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        _ = attrs
        lowered = tag.lower()
        if lowered in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if lowered in {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._chunks.append(" ")

    @override
    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    @override
    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if data:
            self._chunks.append(data)

    def visible_text(self) -> str:
        return " ".join("".join(self._chunks).split())


def looks_like_html(text: str) -> bool:
    stripped = text.lstrip().lower()
    if not stripped:
        return False
    return stripped.startswith(_HTML_PREFIXES)


def html_to_visible_text(html: str) -> str:
    if not html.strip():
        return ""
    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    return parser.visible_text()


def mail_visible_text(*, body_text: str | None, body_html: str | None) -> str:
    if body_text is not None and body_text.strip():
        if looks_like_html(body_text):
            return html_to_visible_text(body_text)
        return " ".join(body_text.split())
    if body_html is not None and body_html.strip():
        return html_to_visible_text(body_html)
    return ""


def mail_snippet(
    *,
    body_text: str | None,
    body_html: str | None,
    limit: int = 160,
) -> str:
    visible = mail_visible_text(body_text=body_text, body_html=body_html)
    if not visible:
        return ""
    if len(visible) <= limit:
        return visible
    return f"{visible[: limit - 3]}..."
