"""
Перевод сырого HTML из markdown в узлы схемы wiki.

Markdown разрешает HTML, и реальные файлы им пользуются: `<br>` для переноса,
`<details>` для сворачиваемого блока, `<img>` с размерами. Отклонять такой файл
целиком бессмысленно, а вставлять HTML в документ нельзя — источник правды
типизирован схемой. Поэтому известные теги переводятся в узлы и марки, а
остальные разворачиваются или отбрасываются с заметкой.

Санитизация здесь не нужна: результат разбора — не HTML, а узлы схемы, и тег,
которого нет в таблицах ниже, физически не может попасть в документ.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Final, override

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_notices import (
    WikiMarkdownNotice,
    WikiMarkdownNoticeCollector,
    WikiMarkdownNoticeKind,
)
from apps.wiki.content.prosemirror import ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import (
    FOOTNOTE_REFERENCE_NODE,
    MATH_INLINE_NODE,
    MAX_HEADING_LEVEL,
    MENTION_NODE,
)

INLINE_MARK_BY_TAG: Final[dict[str, str]] = {
    "b": "strong",
    "strong": "strong",
    "i": "em",
    "em": "em",
    "s": "strike",
    "del": "strike",
    "strike": "strike",
    "code": "code",
    "mark": "highlight",
}

BLOCK_NODE_BY_TAG: Final[dict[str, str]] = {
    "p": "paragraph",
    "blockquote": "blockquote",
    "ul": "bullet_list",
    "ol": "ordered_list",
    "li": "list_item",
    "hr": "horizontal_rule",
    "pre": "code_block",
    "table": "table",
    "tr": "table_row",
    "th": "table_header",
    "td": "table_cell",
    "details": "toggle",
    "summary": "toggle_summary",
}

TRANSPARENT_TAGS: Final[frozenset[str]] = frozenset(
    {"div", "section", "article", "main", "span", "font", "center", "tbody", "thead", "tfoot"}
)
"""Обёртки без смысла для документа: содержимое поднимается на их место."""

DISCARDED_TAGS: Final[frozenset[str]] = frozenset(
    {"script", "style", "noscript", "iframe", "svg", "form", "input", "button", "template"}
)
"""Теги, содержимое которых не является текстом страницы."""

_HEADING_TAGS: Final[dict[str, int]] = {
    f"h{level}": level for level in range(1, MAX_HEADING_LEVEL + 1)
}

_VOID_TAGS: Final[frozenset[str]] = frozenset({"br", "img", "hr", "input"})

_WHITESPACE_RE: Final[re.Pattern[str]] = re.compile(r"\s+")

INLINE_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {
        "text",
        "hard_break",
        MENTION_NODE,
        FOOTNOTE_REFERENCE_NODE,
        MATH_INLINE_NODE,
    }
)
"""Узлы, которые схема допускает внутри `inline*`."""


class HtmlTag(WikiBaseModel):
    """Разобранный одиночный тег из inline-HTML."""

    name: str
    closing: bool = False
    attrs: dict[str, str] = {}


class _TagReader(HTMLParser):
    """Достаёт из строки первый тег: имя, закрывающий ли он, атрибуты."""

    tag: HtmlTag | None

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tag = None

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.tag is None:
            self.tag = HtmlTag(name=tag, attrs=_attrs_to_dict(attrs))

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    @override
    def handle_endtag(self, tag: str) -> None:
        if self.tag is None:
            self.tag = HtmlTag(name=tag, closing=True)


def _attrs_to_dict(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
    return {name: value for name, value in attrs if value is not None}


def parse_tag(raw: str) -> HtmlTag | None:
    """Разобрать одиночный тег inline-HTML; `None`, если тега там нет."""
    reader = _TagReader()
    reader.feed(raw)
    reader.close()
    return reader.tag


def image_node_from_attrs(attrs: dict[str, str]) -> ProseMirrorNode | None:
    """`<img>` в узел изображения; без `src` изображения не существует."""
    src = attrs.get("src", "")
    if not src:
        return None
    return ProseMirrorNode(
        type="image",
        attrs={
            "src": src,
            "alt": attrs.get("alt", ""),
            "title": attrs.get("title", ""),
            "file_id": "",
        },
    )


class _FragmentBuilder(HTMLParser):
    """Собирает блоки схемы из HTML-фрагмента.

    Дерево строится стеком: у каждого открытого тега свой список детей. Текст
    вне блочного тега оборачивается в абзац — иначе он потерялся бы, а это
    обычный случай для `<div>текст</div>`.
    """

    _notices: WikiMarkdownNoticeCollector
    _discard_depth: int

    def __init__(self, notices: WikiMarkdownNoticeCollector) -> None:
        super().__init__(convert_charrefs=True)
        self._notices = notices
        self._root: list[ProseMirrorNode] = []
        self._stack: list[tuple[str, list[ProseMirrorNode]]] = []
        self._marks: list[ProseMirrorMark] = []
        self._discard_depth = 0

    # --- стек ---

    def _children(self) -> list[ProseMirrorNode]:
        return self._stack[-1][1] if self._stack else self._root

    def _open_tags(self) -> list[str]:
        return [tag for tag, _ in self._stack]

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._discard_depth > 0:
            self._discard_depth += 1
            return
        attr_map = _attrs_to_dict(attrs)

        if tag in DISCARDED_TAGS:
            self._discard_depth = 1
            self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, f"<{tag}> и его содержимое")
            return
        if tag == "br":
            self._children().append(ProseMirrorNode(type="hard_break"))
            return
        if tag == "img":
            image = image_node_from_attrs(attr_map)
            if image is None:
                self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, "<img> без src")
                return
            self._children().append(image)
            return
        if tag == "hr":
            self._children().append(ProseMirrorNode(type="horizontal_rule"))
            return
        if tag == "a":
            href = attr_map.get("href", "")
            if href:
                self._marks.append(
                    ProseMirrorMark(
                        type="link", attrs={"href": href, "title": attr_map.get("title", "")}
                    )
                )
                return
            self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, "<a> без href")
            return
        if tag in INLINE_MARK_BY_TAG and "pre" not in self._open_tags():
            self._marks.append(ProseMirrorMark(type=INLINE_MARK_BY_TAG[tag]))
            return
        if tag in _HEADING_TAGS:
            self._stack.append((tag, []))
            return
        if tag in BLOCK_NODE_BY_TAG:
            self._stack.append((tag, []))
            return
        if tag in TRANSPARENT_TAGS:
            self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, f"обёртка <{tag}>")
            return
        self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, f"<{tag}>")

    @override
    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID_TAGS:
            self.handle_endtag(tag)

    @override
    def handle_endtag(self, tag: str) -> None:
        if self._discard_depth > 0:
            self._discard_depth -= 1
            return
        if tag in _VOID_TAGS:
            return
        if tag == "a" or (tag in INLINE_MARK_BY_TAG and "pre" not in self._open_tags()):
            if self._marks:
                _ = self._marks.pop()
            return
        if not self._stack or self._stack[-1][0] != tag:
            return
        _, children = self._stack.pop()
        node = self._finish_block(tag, children)
        if node is not None:
            self._children().append(node)

    def _finish_block(self, tag: str, children: list[ProseMirrorNode]) -> ProseMirrorNode | None:
        if tag in _HEADING_TAGS:
            if not children:
                return None
            return ProseMirrorNode(
                type="heading", attrs={"level": _HEADING_TAGS[tag]}, content=children
            )
        node_type = BLOCK_NODE_BY_TAG[tag]
        if node_type == "code_block":
            code = "".join(child.text or "" for child in children)
            content = [ProseMirrorNode(type="text", text=code)] if code else []
            return ProseMirrorNode(type="code_block", attrs={"language": ""}, content=content)
        if node_type == "paragraph":
            return ProseMirrorNode(type="paragraph", content=children)
        if not children:
            return None
        return ProseMirrorNode(type=node_type, content=_as_blocks(node_type, children))

    @override
    def handle_data(self, data: str) -> None:
        if self._discard_depth > 0:
            return
        if "pre" in self._open_tags():
            if data:
                self._children().append(ProseMirrorNode(type="text", text=data))
            return

        # Пробелы схлопываются, но не срезаются: в `с <b>жирным</b> и` они
        # разделяют слова, и обрезка склеила бы текст в одно слово.
        collapsed = _WHITESPACE_RE.sub(" ", data)
        if collapsed.strip() == "":
            children = self._children()
            if not children or children[-1].type not in INLINE_NODE_TYPES:
                return
            collapsed = " "
        self._children().append(
            ProseMirrorNode(type="text", text=collapsed, marks=list(self._marks))
        )

    def result(self) -> list[ProseMirrorNode]:
        while self._stack:
            tag, children = self._stack.pop()
            node = self._finish_block(tag, children)
            if node is not None:
                self._children().append(node)
        return _as_blocks("doc", self._root)


_INLINE_CONTAINER_TYPES: Final[frozenset[str]] = frozenset(
    {"paragraph", "heading", "toggle_summary", "code_block"}
)

_BLOCK_CONTAINERS_NEEDING_BLOCKS: Final[frozenset[str]] = frozenset(
    {"doc", "blockquote", "list_item", "table_cell", "table_header", "toggle"}
)


def _as_blocks(container_type: str, nodes: list[ProseMirrorNode]) -> list[ProseMirrorNode]:
    """Обернуть inline-узлы в абзац там, где схема требует блоки."""
    if container_type in _INLINE_CONTAINER_TYPES:
        return nodes
    if container_type not in _BLOCK_CONTAINERS_NEEDING_BLOCKS:
        return nodes

    blocks: list[ProseMirrorNode] = []
    inline_run: list[ProseMirrorNode] = []
    for node in nodes:
        if node.type in INLINE_NODE_TYPES:
            inline_run.append(node)
            continue
        if inline_run:
            blocks.append(ProseMirrorNode(type="paragraph", content=inline_run))
            inline_run = []
        blocks.append(node)
    if inline_run:
        blocks.append(ProseMirrorNode(type="paragraph", content=inline_run))
    return blocks


def html_fragment_to_blocks(
    raw: str,
) -> tuple[list[ProseMirrorNode], list[WikiMarkdownNotice]]:
    """Блоки схемы из HTML-фрагмента плюс заметки о потерянном."""
    notices = WikiMarkdownNoticeCollector()
    builder = _FragmentBuilder(notices)
    builder.feed(raw)
    builder.close()
    return builder.result(), notices.result()


def normalize_align(value: str) -> str:
    """`text-align: center` из атрибута style в значение схемы."""
    compact = value.lower().replace(" ", "")
    for candidate in ("left", "center", "right"):
        if f"text-align:{candidate}" in compact:
            return candidate
    return ""


__all__ = [
    "BLOCK_NODE_BY_TAG",
    "DISCARDED_TAGS",
    "INLINE_MARK_BY_TAG",
    "TRANSPARENT_TAGS",
    "HtmlTag",
    "html_fragment_to_blocks",
    "image_node_from_attrs",
    "normalize_align",
    "parse_tag",
]
