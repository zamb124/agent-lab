"""
Разбор markdown в документ wiki.

Нужен на сервере: AI-инструменты создают и правят страницы markdown-ом, а
источник правды — `ProseMirrorNode`. Поддерживается ровно то подмножество,
которое умеет писать `markdown_serializer`; всё остальное — ошибка, потому что
молча выбросить кусок пользовательского текста хуже, чем отказать.
"""

from __future__ import annotations

import re
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token

from apps.wiki.content.markdown_serializer import MENTION_LINK_SCHEME, PLATFORM_FILE_SCHEME
from apps.wiki.content.prosemirror import ProseMirrorAttrValue, ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import (
    MAX_HEADING_LEVEL,
    WikiCalloutTone,
    WikiMentionKind,
    WikiSchemaError,
    normalize_document,
)

_MENTION_SCHEME_TO_KIND: Final[dict[str, WikiMentionKind]] = {
    scheme: kind for kind, scheme in MENTION_LINK_SCHEME.items()
}

_ALERT_RE: Final[re.Pattern[str]] = re.compile(r"^\[!([A-Za-z]+)\]\s*(.*)$")
_TASK_RE: Final[re.Pattern[str]] = re.compile(r"^\[([ xX])\]\s+")
_HIGHLIGHT_MARKER: Final[str] = "=="
_MENTION_MARK: Final[str] = "__mention__"


class WikiMarkdownError(ValueError):
    """Markdown содержит конструкцию, которой нет в схеме wiki."""


def _highlight_rule(state: StateInline, silent: bool) -> bool:
    """Inline-правило для `==текст==`.

    В CommonMark подсветки нет, а `mdit_py_plugins` в зависимостях платформы
    отсутствует, поэтому правило регистрируется вручную — иначе markdown,
    записанный сериализатором, не читался бы обратно.
    """
    position = state.pos
    if not state.src.startswith(_HIGHLIGHT_MARKER, position):
        return False
    closing = state.src.find(_HIGHLIGHT_MARKER, position + 2)
    if closing == -1 or closing == position + 2:
        return False
    if silent:
        return True

    saved_max = state.posMax
    state.pos = position + 2
    state.posMax = closing
    open_token = state.push("highlight_open", "mark", 1)
    open_token.markup = _HIGHLIGHT_MARKER
    state.md.inline.tokenize(state)
    close_token = state.push("highlight_close", "mark", -1)
    close_token.markup = _HIGHLIGHT_MARKER
    state.pos = closing + 2
    state.posMax = saved_max
    return True


def _build_markdown_it() -> MarkdownIt:
    parser = MarkdownIt("commonmark")
    _ = parser.enable("table")
    _ = parser.enable("strikethrough")
    parser.inline.ruler.before("emphasis", "wiki_highlight", _highlight_rule)
    return parser


_MD: Final[MarkdownIt] = _build_markdown_it()

_MARK_OPEN_TOKENS: Final[dict[str, str]] = {
    "strong_open": "strong",
    "em_open": "em",
    "s_open": "strike",
    "highlight_open": "highlight",
}

_MARK_CLOSE_TOKENS: Final[frozenset[str]] = frozenset(
    {"strong_close", "em_close", "s_close", "highlight_close"}
)

_CONTAINER_TOKENS: Final[dict[str, str]] = {
    "paragraph_open": "paragraph",
    "blockquote_open": "blockquote",
    "bullet_list_open": "bullet_list",
    "ordered_list_open": "ordered_list",
    "list_item_open": "list_item",
    "table_open": "table",
    "tr_open": "table_row",
    "th_open": "table_header",
    "td_open": "table_cell",
}

_IGNORED_TOKENS: Final[frozenset[str]] = frozenset(
    {"thead_open", "thead_close", "tbody_open", "tbody_close"}
)

_INLINE_ONLY_CONTAINERS: Final[frozenset[str]] = frozenset({"paragraph", "heading"})


def _mark(mark_type: str, attrs: dict[str, ProseMirrorAttrValue] | None = None) -> ProseMirrorMark:
    return ProseMirrorMark(type=mark_type, attrs=dict(attrs) if attrs else {})


def _inline_children(token: Token) -> list[Token]:
    children = token.children
    return list(children) if children else []


def _finish_mention(nodes: list[ProseMirrorNode], mark: ProseMirrorMark) -> None:
    """Свернуть накопленный текст ссылки в узел упоминания."""
    label_parts: list[str] = []
    while nodes:
        last = nodes[-1]
        if last.type != "text" or not any(inner.type == _MENTION_MARK for inner in last.marks):
            break
        label_parts.insert(0, last.text or "")
        _ = nodes.pop()

    scheme = mark.attrs.get("scheme")
    target = mark.attrs.get("target")
    if not isinstance(scheme, str) or not isinstance(target, str) or not target:
        raise WikiMarkdownError("Упоминание без цели")
    nodes.append(
        ProseMirrorNode(
            type="platform_mention",
            attrs={
                "mention_kind": _MENTION_SCHEME_TO_KIND[scheme].value,
                "target_id": target,
                "label": "".join(label_parts),
            },
        )
    )


def _parse_inline(tokens: list[Token]) -> list[ProseMirrorNode]:
    nodes: list[ProseMirrorNode] = []
    active_marks: list[ProseMirrorMark] = []
    text_ends_with_at = False

    for token in tokens:
        token_type = token.type

        if token_type == "text":
            text = token.content
            text_ends_with_at = text.endswith("@")
            if text_ends_with_at:
                text = text[:-1]
            if text:
                nodes.append(ProseMirrorNode(type="text", text=text, marks=list(active_marks)))
            continue

        if token_type == "softbreak":
            text_ends_with_at = False
            nodes.append(ProseMirrorNode(type="text", text=" ", marks=list(active_marks)))
            continue

        if token_type == "hardbreak":
            text_ends_with_at = False
            nodes.append(ProseMirrorNode(type="hard_break"))
            continue

        if token_type == "code_inline":
            text_ends_with_at = False
            nodes.append(
                ProseMirrorNode(
                    type="text",
                    text=token.content,
                    marks=[*active_marks, _mark("code")],
                )
            )
            continue

        if token_type == "image":
            text_ends_with_at = False
            src = token.attrGet("src")
            if not isinstance(src, str) or not src:
                raise WikiMarkdownError("Изображение без src")
            title = token.attrGet("title")
            nodes.append(
                ProseMirrorNode(
                    type="image",
                    attrs={
                        "src": src,
                        "alt": token.content,
                        "title": title if isinstance(title, str) else "",
                        "file_id": "",
                    },
                )
            )
            continue

        if token_type in _MARK_OPEN_TOKENS:
            text_ends_with_at = False
            active_marks.append(_mark(_MARK_OPEN_TOKENS[token_type]))
            continue

        if token_type in _MARK_CLOSE_TOKENS:
            if active_marks:
                _ = active_marks.pop()
            continue

        if token_type == "link_open":
            href = token.attrGet("href")
            if not isinstance(href, str) or not href:
                raise WikiMarkdownError("Ссылка без href")
            scheme, _, target = href.partition(":")
            if text_ends_with_at and scheme in _MENTION_SCHEME_TO_KIND:
                active_marks.append(_mark(_MENTION_MARK, {"scheme": scheme, "target": target}))
            else:
                title = token.attrGet("title")
                active_marks.append(
                    _mark("link", {"href": href, "title": title if isinstance(title, str) else ""})
                )
            text_ends_with_at = False
            continue

        if token_type == "link_close":
            if not active_marks:
                continue
            mark = active_marks.pop()
            if mark.type == _MENTION_MARK:
                _finish_mention(nodes, mark)
            continue

        raise WikiMarkdownError(f"Inline-конструкция {token_type} не поддержана")

    return nodes


def _standalone_block_from_paragraph(node: ProseMirrorNode) -> ProseMirrorNode:
    """Абзац из единственного специального элемента становится блоком.

    Так `![alt](src)` превращается в блок изображения, а
    `[отчёт](platform-file:...)` — в карточку документа, а не остаётся
    обычной ссылкой внутри текста.
    """
    if len(node.content) != 1:
        return node
    child = node.content[0]

    if child.type == "image":
        return child

    if child.type != "text" or len(child.marks) != 1:
        return node
    mark = child.marks[0]
    if mark.type != "link":
        return node
    href = mark.attrs.get("href")
    if not isinstance(href, str):
        return node
    scheme, _, target = href.partition(":")
    if scheme != PLATFORM_FILE_SCHEME or not target:
        return node
    return ProseMirrorNode(
        type="platform_file",
        attrs={"file_id": target, "original_name": child.text or "", "content_type": ""},
    )


def _convert_alert_blockquote(node: ProseMirrorNode) -> ProseMirrorNode:
    """Цитата с маркером `[!TONE]` — это callout, с `[!TOGGLE]` — сворачиваемый блок."""
    if not node.content:
        return node
    head = node.content[0]
    if head.type != "paragraph" or not head.content:
        return node
    first = head.content[0]
    if first.type != "text" or first.text is None:
        return node
    match = _ALERT_RE.match(first.text.lstrip())
    if match is None:
        return node

    marker = match.group(1).upper()
    remainder = match.group(2)
    tail = node.content[1:]
    rest_inline = head.content[1:]

    if marker == "TOGGLE":
        summary: list[ProseMirrorNode] = []
        if remainder:
            summary.append(ProseMirrorNode(type="text", text=remainder))
        summary.extend(rest_inline)
        body = tail if tail else [ProseMirrorNode(type="paragraph")]
        return ProseMirrorNode(
            type="toggle",
            content=[ProseMirrorNode(type="toggle_summary", content=summary), *body],
        )

    tone_by_marker = {member.value.upper(): member for member in WikiCalloutTone}
    tone = tone_by_marker.get(marker)
    if tone is None:
        return node

    body: list[ProseMirrorNode] = []
    head_inline: list[ProseMirrorNode] = []
    if remainder:
        head_inline.append(ProseMirrorNode(type="text", text=remainder))
    head_inline.extend(rest_inline)
    if head_inline:
        body.append(ProseMirrorNode(type="paragraph", content=head_inline))
    body.extend(tail)
    if not body:
        body = [ProseMirrorNode(type="paragraph")]
    return ProseMirrorNode(type="callout", attrs={"tone": tone.value}, content=body)


def _convert_task_list(node: ProseMirrorNode) -> ProseMirrorNode:
    """Список, каждый пункт которого начинается с `[ ]`, — это чек-лист."""
    if not node.content:
        return node

    checks: list[bool] = []
    for item in node.content:
        if not item.content or item.content[0].type != "paragraph":
            return node
        paragraph = item.content[0]
        if not paragraph.content or paragraph.content[0].type != "text":
            return node
        match = _TASK_RE.match(paragraph.content[0].text or "")
        if match is None:
            return node
        checks.append(match.group(1).lower() == "x")

    items: list[ProseMirrorNode] = []
    for item, checked in zip(node.content, checks, strict=True):
        paragraph = item.content[0]
        first_text = paragraph.content[0]
        stripped = _TASK_RE.sub("", first_text.text or "", count=1)
        inline: list[ProseMirrorNode] = []
        if stripped:
            inline.append(
                ProseMirrorNode(type="text", text=stripped, marks=list(first_text.marks))
            )
        inline.extend(paragraph.content[1:])
        items.append(
            ProseMirrorNode(
                type="task_item",
                attrs={"checked": checked},
                content=[
                    ProseMirrorNode(type="paragraph", content=inline),
                    *item.content[1:],
                ],
            )
        )
    return ProseMirrorNode(type="task_list", content=items)


def _finalize_block(node: ProseMirrorNode) -> ProseMirrorNode:
    if node.type == "paragraph":
        return _standalone_block_from_paragraph(node)
    if node.type == "blockquote":
        return _convert_alert_blockquote(node)
    if node.type == "bullet_list":
        return _convert_task_list(node)
    return node


class _TreeBuilder:
    """Сборка дерева из плоского потока токенов markdown-it."""

    def __init__(self) -> None:
        self._root: list[ProseMirrorNode] = []
        self._stack: list[tuple[ProseMirrorNode, list[ProseMirrorNode]]] = []

    def current_type(self) -> str | None:
        return self._stack[-1][0].type if self._stack else None

    def _children(self) -> list[ProseMirrorNode]:
        return self._stack[-1][1] if self._stack else self._root

    def open(self, node: ProseMirrorNode) -> None:
        self._stack.append((node, []))

    def close(self) -> None:
        if not self._stack:
            raise WikiMarkdownError("Непарный закрывающий токен markdown")
        node, children = self._stack.pop()
        finalized = _finalize_block(
            ProseMirrorNode(type=node.type, attrs=node.attrs, content=children)
        )
        self._children().append(finalized)

    def add(self, node: ProseMirrorNode) -> None:
        self._children().append(_finalize_block(node))

    def extend(self, nodes: list[ProseMirrorNode]) -> None:
        self._children().extend(nodes)

    def result(self) -> list[ProseMirrorNode]:
        if self._stack:
            raise WikiMarkdownError("Незакрытый блок markdown")
        return self._root


def markdown_to_document(markdown_text: str) -> ProseMirrorNode:
    """Собрать документ из markdown.

    Результат нормализуется по схеме, поэтому дальше по пайплайну попадает
    уже валидный контент с проставленными атрибутами.
    """
    builder = _TreeBuilder()

    for token in _MD.parse(markdown_text):
        token_type = token.type

        if token_type in _IGNORED_TOKENS:
            continue

        if token_type == "inline":
            inline_nodes = _parse_inline(_inline_children(token))
            if builder.current_type() in _INLINE_ONLY_CONTAINERS:
                builder.extend(inline_nodes)
            else:
                builder.add(ProseMirrorNode(type="paragraph", content=inline_nodes))
            continue

        if token_type == "heading_open":
            level = min(int(token.tag[1:]), MAX_HEADING_LEVEL)
            builder.open(ProseMirrorNode(type="heading", attrs={"level": level}))
            continue

        if token_type == "heading_close":
            builder.close()
            continue

        if token_type in _CONTAINER_TOKENS:
            node_type = _CONTAINER_TOKENS[token_type]
            attrs: dict[str, ProseMirrorAttrValue] = {}
            if node_type == "ordered_list":
                start = token.attrGet("start")
                attrs["start"] = int(start) if start is not None else 1
            builder.open(ProseMirrorNode(type=node_type, attrs=attrs))
            continue

        if token_type.endswith("_close") and f"{token_type[:-6]}_open" in _CONTAINER_TOKENS:
            builder.close()
            continue

        if token_type in {"fence", "code_block"}:
            language = token.info.strip() if token.info else ""
            code = token.content.rstrip("\n")
            content = [ProseMirrorNode(type="text", text=code)] if code else []
            builder.add(
                ProseMirrorNode(type="code_block", attrs={"language": language}, content=content)
            )
            continue

        if token_type == "hr":
            builder.add(ProseMirrorNode(type="horizontal_rule"))
            continue

        raise WikiMarkdownError(f"Блочная конструкция {token_type} не поддержана")

    blocks = builder.result()
    if not blocks:
        blocks = [ProseMirrorNode(type="paragraph")]
    try:
        return normalize_document(ProseMirrorNode(type="doc", content=blocks))
    except WikiSchemaError as exc:
        raise WikiMarkdownError(str(exc)) from exc


__all__ = [
    "WikiMarkdownError",
    "markdown_to_document",
]
