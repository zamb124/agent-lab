"""
Разбор markdown в документ wiki.

Диалект — CommonMark 0.31 плюс расширения GFM и то, что де-факто понимает
GitHub: таблицы с выравниванием, зачёркивание, чек-листы, автоссылки, сноски,
формулы, YAML-шапка. Плюс наши конструкции: `==выделение==`, упоминания
`@[имя](user:id)`, карточки файлов и callout/toggle в синтаксисе alert-цитат.

Разбор не отклоняет файл из-за незнакомой конструкции. Сырой HTML переводится в
узлы схемы по whitelist (`markdown_html`), остальное отбрасывается или
разворачивается, и каждое расхождение попадает в заметки: пользователь должен
видеть, что изменилось, а молча терять его текст нельзя.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Final

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.front_matter import front_matter_plugin
from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.markdown_html import (
    INLINE_MARK_BY_TAG,
    html_fragment_to_blocks,
    image_node_from_attrs,
    normalize_align,
    normalize_code_language,
    parse_tag,
)
from apps.wiki.content.markdown_notices import (
    WikiMarkdownNotice,
    WikiMarkdownNoticeCollector,
    WikiMarkdownNoticeKind,
)
from apps.wiki.content.markdown_serializer import MENTION_LINK_SCHEME, PLATFORM_FILE_SCHEME
from apps.wiki.content.prosemirror import ProseMirrorAttrValue, ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import (
    FOOTNOTE_DEFINITION_NODE,
    FOOTNOTE_REFERENCE_NODE,
    MATH_BLOCK_NODE,
    MATH_INLINE_NODE,
    MAX_HEADING_LEVEL,
    WikiCalloutTone,
    WikiMentionKind,
    WikiSchemaError,
    WikiTableAlign,
    normalize_document,
)

_MENTION_SCHEME_TO_KIND: Final[dict[str, WikiMentionKind]] = {
    scheme: kind for kind, scheme in MENTION_LINK_SCHEME.items()
}

_ALERT_RE: Final[re.Pattern[str]] = re.compile(r"^\[!([A-Za-z]+)\]\s*(.*)$")
_TASK_RE: Final[re.Pattern[str]] = re.compile(r"^\[([ xX])\]\s+")
_HIGHLIGHT_MARKER: Final[str] = "=="
_MENTION_MARK: Final[str] = "__mention__"

_DATA_URI_LIMIT_BYTES: Final[int] = 256 * 1024
"""Порог, после которого встроенная картинка раздувает документ настолько, что
об этом стоит сказать: страница целиком приезжает в каждый ответ API."""


class WikiMarkdownError(ValueError):
    """Markdown не удалось привести к документу схемы."""


class WikiMarkdownParseResult(WikiBaseModel):
    """Документ и всё, что не перенеслось из исходного текста."""

    document: ProseMirrorNode
    notices: list[WikiMarkdownNotice] = Field(default_factory=list)


def _highlight_rule(state: StateInline, silent: bool) -> bool:
    """Inline-правило для `==текст==`.

    Выделения нет ни в CommonMark, ни в плагинах markdown-it, а сериализатор его
    пишет — без своего правила такой markdown не читался бы обратно.
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
    parser = MarkdownIt("commonmark", {"linkify": True, "html": True})
    _ = parser.enable(["table", "strikethrough", "linkify"])
    _ = parser.use(front_matter_plugin)
    _ = parser.use(footnote_plugin)
    # double_inline: `$$формула$$` внутри строки — так пишет GitHub.
    _ = parser.use(dollarmath_plugin, double_inline=True)
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
    {
        "thead_open",
        "thead_close",
        "tbody_open",
        "tbody_close",
        # Шапку файла разбирает markdown_file: свойства страницы живут в БД.
        "front_matter",
        # Обёртка над блоком сносок: сами определения приходят отдельными токенами.
        "footnote_block_open",
        "footnote_block_close",
        # Ссылка «вернуться к тексту» — навигация рендера, а не содержимое.
        "footnote_anchor",
    }
)

_INLINE_ONLY_CONTAINERS: Final[frozenset[str]] = frozenset({"paragraph", "heading"})

_INLINE_NODE_TYPES: Final[frozenset[str]] = frozenset(
    {"text", "hard_break", "platform_mention", FOOTNOTE_REFERENCE_NODE, MATH_INLINE_NODE}
)


def _mark(mark_type: str, attrs: dict[str, ProseMirrorAttrValue] | None = None) -> ProseMirrorMark:
    return ProseMirrorMark(type=mark_type, attrs=dict(attrs) if attrs else {})


def _inline_children(token: Token) -> list[Token]:
    children = token.children
    return list(children) if children else []


def _trim_inline_run(nodes: list[ProseMirrorNode]) -> list[ProseMirrorNode]:
    """Убрать пробелы по краям куска строки, ставшего отдельным абзацем.

    Пробел, который отделял текст от вынесенного изображения, внутри абзаца
    больше ничего не разделяет, а markdown его всё равно не сохранит — без
    обрезки повторный экспорт давал бы другой текст.
    """
    trimmed = list(nodes)
    while trimmed and trimmed[0].type == "text":
        stripped = (trimmed[0].text or "").lstrip()
        if stripped:
            trimmed[0] = trimmed[0].model_copy(update={"text": stripped})
            break
        _ = trimmed.pop(0)
    while trimmed and trimmed[-1].type == "text":
        stripped = (trimmed[-1].text or "").rstrip()
        if stripped:
            trimmed[-1] = trimmed[-1].model_copy(update={"text": stripped})
            break
        _ = trimmed.pop()
    return trimmed


def _token_line(token: Token) -> int | None:
    if token.map is None:
        return None
    return token.map[0] + 1


def _footnote_label(token: Token, prefix: str) -> str:
    """Метка сноски.

    У встроенной формы `^[текст]` метки нет вообще, поэтому она выводится из
    номера: без метки узел схемы не собрать, а терять сноску нельзя.
    """
    meta = token.meta
    raw_label = meta.get("label")
    if isinstance(raw_label, str) and raw_label:
        return raw_label
    raw_id = meta.get("id")
    number = raw_id + 1 if isinstance(raw_id, int) else 1
    return f"{prefix}{number}"


type _BlockFinalizer = Callable[[ProseMirrorNode, str | None], list[ProseMirrorNode]]
"""Доводка закрытого блока: узел плюс тип родителя на входе, блоки на выходе.

Родитель нужен потому, что схема требует от `list_item` начинаться с абзаца, а
вынесенное из абзаца изображение это нарушило бы."""


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

    def close(self, finalize: _BlockFinalizer) -> None:
        if not self._stack:
            raise WikiMarkdownError("Непарный закрывающий токен markdown")
        node, children = self._stack.pop()
        finished = finalize(
            ProseMirrorNode(type=node.type, attrs=node.attrs, content=children),
            self.current_type(),
        )
        self._children().extend(finished)

    def add(self, node: ProseMirrorNode) -> None:
        self._children().append(node)

    def extend(self, nodes: list[ProseMirrorNode]) -> None:
        self._children().extend(nodes)

    def result(self) -> list[ProseMirrorNode]:
        if self._stack:
            raise WikiMarkdownError("Незакрытый блок markdown")
        return self._root


class _MarkdownReader:
    """Один разбор: токены markdown-it в документ плюс заметки о потерях.

    Состояние (заметки, счётчики) держится на экземпляре: разбор идёт в
    параллельных запросах, и общий накопитель смешивал бы страницы.
    """

    _notices: WikiMarkdownNoticeCollector
    _builder: _TreeBuilder

    def __init__(self) -> None:
        self._notices = WikiMarkdownNoticeCollector()
        self._builder = _TreeBuilder()

    # --- inline ---

    def _finish_mention(self, nodes: list[ProseMirrorNode], mark: ProseMirrorMark) -> None:
        """Свернуть накопленный текст ссылки в узел упоминания."""
        label_parts: list[str] = []
        while nodes:
            last = nodes[-1]
            if last.type != "text" or not any(
                inner.type == _MENTION_MARK for inner in last.marks
            ):
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

    def _image_node(self, src: str, alt: str, title: str, line: int | None) -> ProseMirrorNode:
        if src.startswith("data:") and len(src.encode("utf-8")) > _DATA_URI_LIMIT_BYTES:
            self._notices.add(
                WikiMarkdownNoticeKind.OVERSIZED_DATA_URI,
                f"встроенное изображение больше {_DATA_URI_LIMIT_BYTES // 1024} КБ",
                line,
            )
        return ProseMirrorNode(
            type="image",
            attrs={"src": src, "alt": alt, "title": title, "file_id": ""},
        )

    def _note_relative_link(self, href: str, line: int | None) -> None:
        if href.startswith(("http://", "https://", "mailto:", "#", "data:")):
            return
        if ":" in href.split("/")[0]:
            return
        if not href.lower().endswith((".md", ".markdown")):
            return
        self._notices.add(
            WikiMarkdownNoticeKind.UNRESOLVED_PAGE_LINK,
            f"ссылка на файл {href} осталась текстом: импорт одного файла не знает дерева",
            line,
        )

    def _inline_html(
        self, raw: str, active_marks: list[ProseMirrorMark], line: int | None
    ) -> ProseMirrorNode | None:
        """Одиночный inline-тег: открыть/закрыть марку или дать узел."""
        tag = parse_tag(raw)
        if tag is None:
            self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, raw.strip(), line)
            return None

        if tag.name == "br":
            return ProseMirrorNode(type="hard_break")
        if tag.name == "img":
            image = image_node_from_attrs(tag.attrs)
            if image is None:
                self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, "<img> без src", line)
            return image
        if tag.name == "a":
            if tag.closing:
                if active_marks:
                    _ = active_marks.pop()
                return None
            href = tag.attrs.get("href", "")
            if not href:
                self._notices.add(WikiMarkdownNoticeKind.DROPPED_HTML, "<a> без href", line)
                return None
            active_marks.append(
                _mark("link", {"href": href, "title": tag.attrs.get("title", "")})
            )
            return None
        if tag.name in INLINE_MARK_BY_TAG:
            if tag.closing:
                if active_marks:
                    _ = active_marks.pop()
                return None
            active_marks.append(_mark(INLINE_MARK_BY_TAG[tag.name]))
            return None

        self._notices.add(
            WikiMarkdownNoticeKind.DROPPED_HTML, f"<{tag.name}> внутри текста", line
        )
        return None

    def _parse_inline(self, tokens: list[Token], line: int | None) -> list[ProseMirrorNode]:
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
                    nodes.append(
                        ProseMirrorNode(type="text", text=text, marks=list(active_marks))
                    )
                continue

            if token_type == "softbreak":
                text_ends_with_at = False
                nodes.append(
                    ProseMirrorNode(type="text", text=" ", marks=list(active_marks))
                )
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

            if token_type in {"math_inline", "math_inline_double"}:
                text_ends_with_at = False
                nodes.append(
                    ProseMirrorNode(type=MATH_INLINE_NODE, attrs={"formula": token.content})
                )
                continue

            if token_type == "footnote_ref":
                text_ends_with_at = False
                nodes.append(
                    ProseMirrorNode(
                        type=FOOTNOTE_REFERENCE_NODE,
                        attrs={"label": _footnote_label(token, "fn")},
                    )
                )
                continue

            if token_type == "image":
                text_ends_with_at = False
                src = token.attrGet("src")
                if not isinstance(src, str) or not src:
                    self._notices.add(
                        WikiMarkdownNoticeKind.UNSUPPORTED_CONSTRUCT,
                        "изображение без src пропущено",
                        line,
                    )
                    continue
                title = token.attrGet("title")
                nodes.append(
                    self._image_node(
                        src,
                        token.content,
                        title if isinstance(title, str) else "",
                        line,
                    )
                )
                continue

            if token_type == "html_inline":
                node = self._inline_html(token.content, active_marks, line)
                if node is not None:
                    nodes.append(node)
                text_ends_with_at = False
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
                    self._notices.add(
                        WikiMarkdownNoticeKind.UNSUPPORTED_CONSTRUCT,
                        "ссылка без href стала текстом",
                        line,
                    )
                    continue
                scheme, _, target = href.partition(":")
                if text_ends_with_at and scheme in _MENTION_SCHEME_TO_KIND:
                    active_marks.append(
                        _mark(_MENTION_MARK, {"scheme": scheme, "target": target})
                    )
                else:
                    self._note_relative_link(href, line)
                    title = token.attrGet("title")
                    active_marks.append(
                        _mark(
                            "link",
                            {"href": href, "title": title if isinstance(title, str) else ""},
                        )
                    )
                text_ends_with_at = False
                continue

            if token_type == "link_close":
                if not active_marks:
                    continue
                mark = active_marks.pop()
                if mark.type == _MENTION_MARK:
                    self._finish_mention(nodes, mark)
                continue

            self._notices.add(
                WikiMarkdownNoticeKind.UNSUPPORTED_CONSTRUCT,
                f"inline-конструкция {token_type} пропущена",
                line,
            )

        return nodes

    # --- блоки ---

    def _paragraph_blocks(
        self, node: ProseMirrorNode, parent_type: str | None
    ) -> list[ProseMirrorNode]:
        """Абзац в блоки: изображения и карточки файлов — самостоятельные узлы.

        `image` и `platform_file` в схеме блочные, поэтому смешанный абзац
        «текст ![картинка] текст» разбивается на последовательность блоков в
        исходном порядке. Иначе документ был бы невалиден для редактора.
        """
        lifted = self._standalone_block(node)
        if lifted is not None:
            return [lifted]

        if not any(child.type == "image" for child in node.content):
            return [node]

        blocks: list[ProseMirrorNode] = []
        inline_run: list[ProseMirrorNode] = []
        for child in node.content:
            if child.type != "image":
                inline_run.append(child)
                continue
            trimmed = _trim_inline_run(inline_run)
            if trimmed:
                blocks.append(ProseMirrorNode(type="paragraph", content=trimmed))
            inline_run = []
            blocks.append(child)
        trimmed = _trim_inline_run(inline_run)
        if trimmed:
            blocks.append(ProseMirrorNode(type="paragraph", content=trimmed))

        self._notices.add(
            WikiMarkdownNoticeKind.IMAGE_EXTRACTED,
            "изображение внутри абзаца вынесено в отдельный блок",
        )
        # `list_item` и `task_item` по схеме начинаются с абзаца.
        if parent_type in {"list_item", "task_item"} and blocks[0].type != "paragraph":
            blocks.insert(0, ProseMirrorNode(type="paragraph"))
        return blocks

    def _standalone_block(self, node: ProseMirrorNode) -> ProseMirrorNode | None:
        """Абзац из единственного специального элемента становится блоком.

        Так `![alt](src)` превращается в блок изображения, а
        `[отчёт](platform-file:...)` — в карточку документа, а не остаётся
        обычной ссылкой внутри текста.
        """
        if len(node.content) != 1:
            return None
        child = node.content[0]

        if child.type == "image":
            return child

        if child.type != "text" or len(child.marks) != 1:
            return None
        mark = child.marks[0]
        if mark.type != "link":
            return None
        href = mark.attrs.get("href")
        if not isinstance(href, str):
            return None
        scheme, _, target = href.partition(":")
        if scheme != PLATFORM_FILE_SCHEME or not target:
            return None
        return ProseMirrorNode(
            type="platform_file",
            attrs={"file_id": target, "original_name": child.text or "", "content_type": ""},
        )

    def _convert_alert_blockquote(self, node: ProseMirrorNode) -> ProseMirrorNode:
        """Цитата с маркером `[!TONE]` — callout, с `[!TOGGLE]` — сворачиваемый блок."""
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
                content=[
                    # Маркер `[!TOGGLE]` съедает перевод строки после себя, и
                    # оставшийся от него пробел markdown обратно не прочитает.
                    ProseMirrorNode(
                        type="toggle_summary", content=_trim_inline_run(summary)
                    ),
                    *body,
                ],
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
        head_inline = _trim_inline_run(head_inline)
        if head_inline:
            body.append(ProseMirrorNode(type="paragraph", content=head_inline))
        body.extend(tail)
        if not body:
            body = [ProseMirrorNode(type="paragraph")]
        return ProseMirrorNode(type="callout", attrs={"tone": tone.value}, content=body)

    def _convert_task_list(self, node: ProseMirrorNode) -> ProseMirrorNode:
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

    def _finalize_block(
        self, node: ProseMirrorNode, parent_type: str | None
    ) -> list[ProseMirrorNode]:
        if node.type == "paragraph":
            return self._paragraph_blocks(node, parent_type)
        if node.type == "blockquote":
            return [self._convert_alert_blockquote(node)]
        if node.type == "bullet_list":
            return [self._convert_task_list(node)]
        return [node]

    # --- поток токенов ---

    def _cell_align(self, token: Token) -> str:
        style = token.attrGet("style")
        if not isinstance(style, str):
            return WikiTableAlign.NONE.value
        return normalize_align(style)

    def _read_tokens(self, tokens: list[Token]) -> None:
        for token in tokens:
            token_type = token.type
            line = _token_line(token)

            if token_type in _IGNORED_TOKENS:
                continue

            if token_type == "inline":
                inline_nodes = self._parse_inline(_inline_children(token), line)
                if self._builder.current_type() in _INLINE_ONLY_CONTAINERS:
                    self._builder.extend(inline_nodes)
                else:
                    self._builder.extend(
                        self._finalize_block(
                            ProseMirrorNode(type="paragraph", content=inline_nodes),
                            self._builder.current_type(),
                        )
                    )
                continue

            if token_type == "heading_open":
                level = min(int(token.tag[1:]), MAX_HEADING_LEVEL)
                self._builder.open(ProseMirrorNode(type="heading", attrs={"level": level}))
                continue

            if token_type == "heading_close":
                self._builder.close(self._finalize_block)
                continue

            if token_type == "footnote_open":
                self._builder.open(
                    ProseMirrorNode(
                        type=FOOTNOTE_DEFINITION_NODE,
                        attrs={"label": _footnote_label(token, "fn")},
                    )
                )
                continue

            if token_type == "footnote_close":
                self._builder.close(self._finalize_block)
                continue

            if token_type in _CONTAINER_TOKENS:
                node_type = _CONTAINER_TOKENS[token_type]
                attrs: dict[str, ProseMirrorAttrValue] = {}
                if node_type == "ordered_list":
                    start = token.attrGet("start")
                    attrs["start"] = int(start) if start is not None else 1
                if node_type in {"table_cell", "table_header"}:
                    attrs["align"] = self._cell_align(token)
                self._builder.open(ProseMirrorNode(type=node_type, attrs=attrs))
                continue

            if token_type.endswith("_close") and f"{token_type[:-6]}_open" in _CONTAINER_TOKENS:
                self._builder.close(self._finalize_block)
                continue

            if token_type in {"fence", "code_block"}:
                language = normalize_code_language(token.info if token.info else "")
                code = token.content.rstrip("\n")
                content = [ProseMirrorNode(type="text", text=code)] if code else []
                self._builder.add(
                    ProseMirrorNode(
                        type="code_block", attrs={"language": language}, content=content
                    )
                )
                continue

            if token_type == "math_block":
                self._builder.add(
                    ProseMirrorNode(
                        type=MATH_BLOCK_NODE, attrs={"formula": token.content.strip()}
                    )
                )
                continue

            if token_type == "hr":
                self._builder.add(ProseMirrorNode(type="horizontal_rule"))
                continue

            if token_type == "html_block":
                blocks, notices = html_fragment_to_blocks(token.content)
                self._notices.extend(notices)
                self._builder.extend(blocks)
                continue

            self._notices.add(
                WikiMarkdownNoticeKind.UNSUPPORTED_CONSTRUCT,
                f"блок {token_type} пропущен",
                line,
            )

    def read(self, markdown_text: str) -> WikiMarkdownParseResult:
        self._read_tokens(_MD.parse(markdown_text))
        blocks = self._builder.result()
        if not blocks:
            blocks = [ProseMirrorNode(type="paragraph")]
        try:
            document = normalize_document(ProseMirrorNode(type="doc", content=blocks))
        except WikiSchemaError as exc:
            raise WikiMarkdownError(str(exc)) from exc
        return WikiMarkdownParseResult(document=document, notices=self._notices.result())


def parse_markdown(markdown_text: str) -> WikiMarkdownParseResult:
    """Разобрать markdown в документ и заметки о расхождениях.

    Единственная реализация разбора; `markdown_to_document` — обёртка над ней.
    """
    return _MarkdownReader().read(markdown_text)


def markdown_to_document(markdown_text: str) -> ProseMirrorNode:
    """Документ из markdown без отчёта.

    Форма для вызовов, которым некуда показать заметки: создание и правка
    страницы по markdown из API, в том числе агентами. Сами заметки там пишет в
    лог сервис — расхождение не должно оставаться совсем незамеченным.
    """
    return parse_markdown(markdown_text).document


__all__ = [
    "WikiMarkdownError",
    "WikiMarkdownParseResult",
    "markdown_to_document",
    "parse_markdown",
]
