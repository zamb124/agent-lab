"""
Сериализация документа wiki в markdown.

Markdown — производное представление: его читают RAG, LLM и экспорт, но
источник правды всегда `ProseMirrorNode`. Порядок марок и нормализация
атрибутов фиксированы схемой, иначе один и тот же документ давал бы разный
текст и каждое сохранение выглядело бы как правка.

Обратимое ядро (`markdown_parser` разбирает его обратно): заголовки, абзацы,
списки, задачи, цитаты, код, таблицы, разделители, изображения, ссылки,
упоминания, callout и toggle в синтаксисе alert-цитат.
"""

from __future__ import annotations

import re
from typing import Final

from apps.wiki.content.prosemirror import ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import (
    FOOTNOTE_DEFINITION_NODE,
    FOOTNOTE_REFERENCE_NODE,
    MARK_SERIALIZATION_ORDER,
    MATH_BLOCK_NODE,
    MATH_INLINE_NODE,
    WikiCalloutTone,
    WikiMentionKind,
    WikiSchemaError,
    WikiTableAlign,
    normalize_document,
)

MENTION_LINK_SCHEME: Final[dict[WikiMentionKind, str]] = {
    WikiMentionKind.USER: "user",
    WikiMentionKind.CRM_ENTITY: "entity",
    WikiMentionKind.WIKI_PAGE: "wiki",
    WikiMentionKind.FILE: "file",
}
"""Схемы ссылок для упоминаний.

`entity:` совпадает с каноном упоминаний в заметках Networkle, поэтому один и
тот же markdown понимают и CRM, и wiki.
"""

PLATFORM_FILE_SCHEME: Final[str] = "platform-file"

_ESCAPE_RE: Final[re.Pattern[str]] = re.compile(r"([\\`*_\[\]<$])")
_ESCAPE_PAIR_RE: Final[re.Pattern[str]] = re.compile(r"(~~|==)")
_BLOCK_START_RE: Final[re.Pattern[str]] = re.compile(r"^(\s*)([#>+|-]|\d+[.)])")
_TABLE_CELL_PIPE_RE: Final[re.Pattern[str]] = re.compile(r"\|")


def _escape_text(value: str) -> str:
    """Экранировать только то, что действительно меняет разбор.

    Точки, дефисы и решётки внутри строки безобидны — экранировать их значило
    бы засорять текст обратными слешами; опасное начало строки закрывает
    `_escape_block_start`.
    """
    escaped = _ESCAPE_RE.sub(r"\\\1", value)
    return _ESCAPE_PAIR_RE.sub(lambda match: f"\\{match.group(1)[0]}{match.group(1)[1]}", escaped)


def _escape_block_start(text: str) -> str:
    """Снять двусмысленность у абзаца, начинающегося как другой блок."""
    match = _BLOCK_START_RE.match(text)
    if match is None:
        return text
    indent = match.group(1)
    marker = match.group(2)
    return f"{indent}\\{marker}{text[match.end() :]}"


def _wrap_with_mark(text: str, mark: ProseMirrorMark) -> str:
    if mark.type == "strong":
        return f"**{text}**"
    if mark.type == "em":
        return f"*{text}*"
    if mark.type == "strike":
        return f"~~{text}~~"
    if mark.type == "highlight":
        return f"=={text}=="
    if mark.type == "code":
        return f"`{text}`"
    if mark.type == "link":
        href = mark.attrs.get("href")
        if not isinstance(href, str) or not href:
            raise WikiSchemaError("link.href пуст при сериализации")
        title = mark.attrs.get("title")
        if isinstance(title, str) and title:
            return f'[{text}]({href} "{title}")'
        return f"[{text}]({href})"
    raise WikiSchemaError(f"Марка {mark.type} не поддержана сериализатором")


def _serialize_text_node(node: ProseMirrorNode) -> str:
    if node.text is None:
        raise WikiSchemaError("Текстовый узел без text")
    has_code = any(mark.type == "code" for mark in node.marks)
    text = node.text if has_code else _escape_text(node.text)
    # Внешняя марка применяется последней, поэтому идём от конца канонического порядка.
    for mark_name in reversed(MARK_SERIALIZATION_ORDER):
        for mark in node.marks:
            if mark.type == mark_name:
                text = _wrap_with_mark(text, mark)
    return text


def _serialize_mention(node: ProseMirrorNode) -> str:
    raw_kind = node.attrs.get("mention_kind")
    if not isinstance(raw_kind, str):
        raise WikiSchemaError("platform_mention.mention_kind отсутствует")
    kind = WikiMentionKind(raw_kind)
    target_id = node.attrs.get("target_id")
    if not isinstance(target_id, str) or not target_id:
        raise WikiSchemaError("platform_mention.target_id пуст")
    label = node.attrs.get("label")
    label_text = label if isinstance(label, str) and label else target_id
    return f"@[{label_text}]({MENTION_LINK_SCHEME[kind]}:{target_id})"


def _required_attr(node: ProseMirrorNode, name: str) -> str:
    value = node.attrs.get(name)
    if not isinstance(value, str) or not value:
        raise WikiSchemaError(f"{node.type}.{name} пуст при сериализации")
    return value


def _serialize_inline(nodes: list[ProseMirrorNode]) -> str:
    parts: list[str] = []
    # Разметка переноса строки съедает пробелы по краям, поэтому они снимаются
    # здесь: иначе повторный разбор давал бы уже другой текст.
    after_break = False
    for node in nodes:
        if node.type == "text":
            text = _serialize_text_node(node)
            parts.append(text.lstrip() if after_break else text)
        elif node.type == "hard_break":
            if parts:
                parts[-1] = parts[-1].rstrip()
            parts.append("  \n")
            after_break = True
            continue
        elif node.type == "platform_mention":
            parts.append(_serialize_mention(node))
        elif node.type == FOOTNOTE_REFERENCE_NODE:
            parts.append(f"[^{_required_attr(node, 'label')}]")
        elif node.type == MATH_INLINE_NODE:
            parts.append(f"${_required_attr(node, 'formula')}$")
        else:
            raise WikiSchemaError(f"Узел {node.type} не является inline")
        after_break = False
    return "".join(parts)


def _indent_block(text: str, prefix: str, first_prefix: str | None = None) -> str:
    lines = text.split("\n")
    head = first_prefix if first_prefix is not None else prefix
    rendered: list[str] = []
    for index, line in enumerate(lines):
        marker = head if index == 0 else prefix
        rendered.append(f"{marker}{line}" if line else marker.rstrip())
    return "\n".join(rendered)


def _align_separator(align: str) -> str:
    """Разделитель столбца по выравниванию ячейки шапки."""
    if align == WikiTableAlign.LEFT.value:
        return ":---"
    if align == WikiTableAlign.CENTER.value:
        return ":---:"
    if align == WikiTableAlign.RIGHT.value:
        return "---:"
    return "---"


def _serialize_table(node: ProseMirrorNode) -> str:
    if not node.content:
        raise WikiSchemaError("Таблица без строк")
    rows: list[list[str]] = []
    for row in node.content:
        cells: list[str] = []
        for cell in row.content:
            # Перевод строки внутри ячейки разрушил бы разметку таблицы,
            # поэтому блоки склеиваются через <br>.
            cell_text = "<br>".join(
                _serialize_block(child).replace("\n", " ").strip() for child in cell.content
            )
            cells.append(_TABLE_CELL_PIPE_RE.sub(r"\\|", cell_text).strip())
        rows.append(cells)

    width = max(len(row) for row in rows)
    normalized = [row + [""] * (width - len(row)) for row in rows]
    header = normalized[0]
    # Выравнивание задаёт шапка: в markdown оно одно на столбец.
    header_cells = node.content[0].content
    aligns: list[str] = []
    for index in range(width):
        raw_align = header_cells[index].attrs.get("align") if index < len(header_cells) else ""
        aligns.append(raw_align if isinstance(raw_align, str) else "")
    body = normalized[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(_align_separator(align) for align in aligns) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _serialize_list(node: ProseMirrorNode) -> str:
    ordered = node.type == "ordered_list"
    start_attr = node.attrs.get("start") if ordered else None
    start = start_attr if isinstance(start_attr, int) else 1
    items: list[str] = []
    for index, item in enumerate(node.content):
        body = _serialize_blocks(item.content)
        marker = f"{start + index}. " if ordered else "- "
        items.append(_indent_block(body, " " * len(marker), marker))
    return "\n".join(items)


def _serialize_task_list(node: ProseMirrorNode) -> str:
    # Маркер `*` вместо `-` разводит чек-лист и обычный список: CommonMark
    # объединяет соседние списки с одинаковым маркером в один.
    items: list[str] = []
    for item in node.content:
        checked = item.attrs.get("checked") is True
        marker = "* [x] " if checked else "* [ ] "
        body = _serialize_blocks(item.content)
        items.append(_indent_block(body, " " * len(marker), marker))
    return "\n".join(items)


def _serialize_callout(node: ProseMirrorNode) -> str:
    raw_tone = node.attrs.get("tone")
    tone = WikiCalloutTone(raw_tone) if isinstance(raw_tone, str) else WikiCalloutTone.INFO
    body = _serialize_blocks(node.content)
    # Пустая строка после маркера обязательна: иначе тело склеится с маркером
    # в один абзац и при обратном разборе станет частью заголовка блока.
    return _indent_block(f"[!{tone.value.upper()}]\n\n{body}", "> ")


def _serialize_toggle(node: ProseMirrorNode) -> str:
    if not node.content:
        raise WikiSchemaError("toggle без содержимого")
    summary_node = node.content[0]
    if summary_node.type != "toggle_summary":
        raise WikiSchemaError("Первый ребёнок toggle должен быть toggle_summary")
    summary = _serialize_inline(summary_node.content)
    body = _serialize_blocks(node.content[1:])
    return _indent_block(f"[!TOGGLE] {summary}\n\n{body}", "> ")


def _serialize_block(node: ProseMirrorNode) -> str:
    if node.type == "paragraph":
        return _escape_block_start(_serialize_inline(node.content))
    if node.type == "heading":
        level = node.attrs.get("level")
        if not isinstance(level, int):
            raise WikiSchemaError("heading.level отсутствует")
        return f"{'#' * level} {_serialize_inline(node.content)}"
    if node.type == "blockquote":
        return _indent_block(_serialize_blocks(node.content), "> ")
    if node.type == "code_block":
        language = node.attrs.get("language")
        lang = language if isinstance(language, str) else ""
        code = "".join(child.text or "" for child in node.content)
        return f"```{lang}\n{code}\n```"
    if node.type in {"bullet_list", "ordered_list"}:
        return _serialize_list(node)
    if node.type == "task_list":
        return _serialize_task_list(node)
    if node.type == "callout":
        return _serialize_callout(node)
    if node.type == "toggle":
        return _serialize_toggle(node)
    if node.type == "horizontal_rule":
        return "---"
    if node.type == "image":
        src = node.attrs.get("src")
        if not isinstance(src, str) or not src:
            raise WikiSchemaError("image.src пуст")
        alt = node.attrs.get("alt")
        alt_text = alt if isinstance(alt, str) else ""
        title = node.attrs.get("title")
        if isinstance(title, str) and title:
            return f'![{alt_text}]({src} "{title}")'
        return f"![{alt_text}]({src})"
    if node.type == "platform_file":
        file_id = node.attrs.get("file_id")
        if not isinstance(file_id, str) or not file_id:
            raise WikiSchemaError("platform_file.file_id пуст")
        original_name = node.attrs.get("original_name")
        label = original_name if isinstance(original_name, str) and original_name else file_id
        return f"[{label}]({PLATFORM_FILE_SCHEME}:{file_id})"
    if node.type == "table":
        return _serialize_table(node)
    if node.type == MATH_BLOCK_NODE:
        return f"$$\n{_required_attr(node, 'formula')}\n$$"
    if node.type == FOOTNOTE_DEFINITION_NODE:
        label = _required_attr(node, "label")
        body = _serialize_blocks(node.content)
        return _indent_block(body, "    ", f"[^{label}]: ")
    raise WikiSchemaError(f"Узел {node.type} не поддержан сериализатором")


def _serialize_blocks(nodes: list[ProseMirrorNode]) -> str:
    blocks = [_serialize_block(node) for node in nodes]
    return "\n\n".join(block for block in blocks if block != "")


def document_to_markdown(document: ProseMirrorNode) -> str:
    """Собрать markdown из документа.

    Документ нормализуется по схеме перед обходом: сериализатор не должен
    угадывать пропущенные атрибуты и порядок марок.

    Определения сносок всегда уезжают в конец файла: markdown не читает
    определение, встреченное посреди текста, как часть предыдущего блока, и
    документ с определением в середине после экспорта стал бы невалидным.
    """
    normalized = normalize_document(document)
    if normalized.type != "doc":
        raise WikiSchemaError(f"Ожидался doc, получен {normalized.type}")
    body = [
        node for node in normalized.content if node.type != FOOTNOTE_DEFINITION_NODE
    ]
    footnotes = [
        node for node in normalized.content if node.type == FOOTNOTE_DEFINITION_NODE
    ]
    return _serialize_blocks([*body, *footnotes]).strip()


def document_to_plain_text(document: ProseMirrorNode) -> str:
    """Текст без разметки — для сниппетов поиска и полнотекстового вектора."""
    normalized = normalize_document(document)
    chunks: list[str] = []

    def walk(node: ProseMirrorNode) -> None:
        if node.type == "text" and node.text:
            chunks.append(node.text)
        elif node.type == "platform_mention":
            label = node.attrs.get("label")
            if isinstance(label, str) and label:
                chunks.append(label)
        elif node.type in {MATH_INLINE_NODE, MATH_BLOCK_NODE}:
            # Формула — часть текста страницы: по ней ищут так же, как по коду.
            formula = node.attrs.get("formula")
            if isinstance(formula, str) and formula:
                chunks.append(formula)
        for child in node.content:
            walk(child)
        if node.type in {"paragraph", "heading", "list_item", "task_item", "table_cell"}:
            chunks.append("\n")

    walk(normalized)
    return re.sub(r"\n{2,}", "\n", "".join(chunks)).strip()


__all__ = [
    "MENTION_LINK_SCHEME",
    "PLATFORM_FILE_SCHEME",
    "document_to_markdown",
    "document_to_plain_text",
]
