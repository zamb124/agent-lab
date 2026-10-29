"""
Каноническая схема документа wiki.

Единственный источник правды о наборе узлов, марок и их атрибутов. Python
валидирует по нему контент и строит markdown; браузерная схема ProseMirror
собирается из сгенерированного `wiki-schema.json`, поэтому расхождение между
слоями невозможно без падения drift-гейта
(`scripts/generate/wiki_prosemirror_schema.py --check`).

DOM-рендер (`toDOM`/`parseDOM`) живёт только в JS: он не влияет на данные,
а его парность с этим реестром проверяется тестом схемы.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from pydantic import Field

from apps.wiki.base_model import WikiBaseModel
from apps.wiki.content.prosemirror import ProseMirrorAttrValue, ProseMirrorMark, ProseMirrorNode
from core.types import JsonObject, JsonValue


class WikiAttrKind(StrEnum):
    """Тип значения атрибута — см. `ProseMirrorAttrValue`."""

    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    INT_LIST = "int_list"


class WikiAttrSpec(WikiBaseModel):
    """Атрибут узла или марки."""

    kind: WikiAttrKind
    default: ProseMirrorAttrValue = None
    required: bool = False


class WikiNodeSpec(WikiBaseModel):
    """Узел схемы.

    `content` и `group` — выражения ProseMirror; они уезжают в JS как есть.
    """

    group: str | None = None
    content: str | None = None
    marks: str | None = None
    inline: bool = False
    atom: bool = False
    defining: bool = False
    isolating: bool = False
    code: bool = False
    draggable: bool = False
    selectable: bool = True
    attrs: dict[str, WikiAttrSpec] = Field(default_factory=dict)


class WikiMarkSpec(WikiBaseModel):
    """Марка схемы."""

    inclusive: bool = True
    spanning: bool = True
    excludes: str | None = None
    attrs: dict[str, WikiAttrSpec] = Field(default_factory=dict)


class WikiMentionKind(StrEnum):
    """Что именно упомянуто нодой `platform_mention`.

    Один узел на четыре источника меню упоминаний: люди, сущности Networkle,
    страницы wiki и документы Documents.
    """

    USER = "user"
    CRM_ENTITY = "crm_entity"
    WIKI_PAGE = "wiki_page"
    FILE = "file"


class WikiCalloutTone(StrEnum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    DANGER = "danger"


class WikiTableAlign(StrEnum):
    """Выравнивание содержимого ячейки.

    Пустое значение — выравнивание не задано; в markdown это `---` без
    двоеточий, и отличать его от явного `:---` нужно, иначе экспорт добавлял бы
    выравнивание, которого автор не просил.
    """

    NONE = ""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


DOC_NODE: Final[str] = "doc"
TEXT_NODE: Final[str] = "text"
PARAGRAPH_NODE: Final[str] = "paragraph"
HEADING_NODE: Final[str] = "heading"
MENTION_NODE: Final[str] = "platform_mention"
FILE_NODE: Final[str] = "platform_file"

MAX_HEADING_LEVEL: Final[int] = 6
"""Столько уровней заголовков есть в markdown; меньше — значит терять h5 и h6."""

FOOTNOTE_DEFINITION_NODE: Final[str] = "footnote_definition"
FOOTNOTE_REFERENCE_NODE: Final[str] = "footnote_reference"
MATH_BLOCK_NODE: Final[str] = "math_block"
MATH_INLINE_NODE: Final[str] = "math_inline"

WIKI_NODES: Final[dict[str, WikiNodeSpec]] = {
    DOC_NODE: WikiNodeSpec(content="block+"),
    PARAGRAPH_NODE: WikiNodeSpec(group="block", content="inline*"),
    HEADING_NODE: WikiNodeSpec(
        group="block",
        content="inline*",
        defining=True,
        attrs={"level": WikiAttrSpec(kind=WikiAttrKind.INT, default=1)},
    ),
    "blockquote": WikiNodeSpec(group="block", content="block+", defining=True),
    "code_block": WikiNodeSpec(
        group="block",
        content="text*",
        marks="",
        code=True,
        defining=True,
        attrs={"language": WikiAttrSpec(kind=WikiAttrKind.STRING, default="")},
    ),
    "bullet_list": WikiNodeSpec(group="block", content="list_item+"),
    "ordered_list": WikiNodeSpec(
        group="block",
        content="list_item+",
        attrs={"start": WikiAttrSpec(kind=WikiAttrKind.INT, default=1)},
    ),
    "list_item": WikiNodeSpec(content="paragraph block*", defining=True),
    "task_list": WikiNodeSpec(group="block", content="task_item+"),
    "task_item": WikiNodeSpec(
        content="paragraph block*",
        defining=True,
        attrs={"checked": WikiAttrSpec(kind=WikiAttrKind.BOOL, default=False)},
    ),
    "toggle": WikiNodeSpec(group="block", content="toggle_summary block+"),
    "toggle_summary": WikiNodeSpec(content="inline*", defining=True),
    "callout": WikiNodeSpec(
        group="block",
        content="block+",
        defining=True,
        attrs={
            "tone": WikiAttrSpec(
                kind=WikiAttrKind.STRING, default=WikiCalloutTone.INFO.value
            ),
            "icon": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
        },
    ),
    "horizontal_rule": WikiNodeSpec(group="block", atom=True),
    FOOTNOTE_DEFINITION_NODE: WikiNodeSpec(
        group="block",
        content="block+",
        defining=True,
        attrs={"label": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True)},
    ),
    MATH_BLOCK_NODE: WikiNodeSpec(
        group="block",
        atom=True,
        attrs={"formula": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True)},
    ),
    "image": WikiNodeSpec(
        group="block",
        atom=True,
        draggable=True,
        attrs={
            "src": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True),
            "alt": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
            "title": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
            "file_id": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
        },
    ),
    "table": WikiNodeSpec(group="block", content="table_row+", isolating=True),
    "table_row": WikiNodeSpec(content="(table_cell | table_header)+"),
    "table_cell": WikiNodeSpec(
        content="block+",
        isolating=True,
        attrs={
            "colspan": WikiAttrSpec(kind=WikiAttrKind.INT, default=1),
            "rowspan": WikiAttrSpec(kind=WikiAttrKind.INT, default=1),
            "colwidth": WikiAttrSpec(kind=WikiAttrKind.INT_LIST, default=None),
            "align": WikiAttrSpec(
                kind=WikiAttrKind.STRING, default=WikiTableAlign.NONE.value
            ),
        },
    ),
    "table_header": WikiNodeSpec(
        content="block+",
        isolating=True,
        attrs={
            "colspan": WikiAttrSpec(kind=WikiAttrKind.INT, default=1),
            "rowspan": WikiAttrSpec(kind=WikiAttrKind.INT, default=1),
            "colwidth": WikiAttrSpec(kind=WikiAttrKind.INT_LIST, default=None),
            "align": WikiAttrSpec(
                kind=WikiAttrKind.STRING, default=WikiTableAlign.NONE.value
            ),
        },
    ),
    FILE_NODE: WikiNodeSpec(
        group="block",
        atom=True,
        draggable=True,
        attrs={
            "file_id": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True),
            "original_name": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
            "content_type": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
        },
    ),
    MENTION_NODE: WikiNodeSpec(
        group="inline",
        inline=True,
        atom=True,
        draggable=True,
        attrs={
            "mention_kind": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True),
            "target_id": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True),
            "label": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
        },
    ),
    FOOTNOTE_REFERENCE_NODE: WikiNodeSpec(
        group="inline",
        inline=True,
        atom=True,
        attrs={"label": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True)},
    ),
    MATH_INLINE_NODE: WikiNodeSpec(
        group="inline",
        inline=True,
        atom=True,
        attrs={"formula": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True)},
    ),
    "hard_break": WikiNodeSpec(group="inline", inline=True, selectable=False),
    TEXT_NODE: WikiNodeSpec(group="inline", inline=True),
}

WIKI_MARKS: Final[dict[str, WikiMarkSpec]] = {
    "link": WikiMarkSpec(
        inclusive=False,
        attrs={
            "href": WikiAttrSpec(kind=WikiAttrKind.STRING, required=True),
            "title": WikiAttrSpec(kind=WikiAttrKind.STRING, default=""),
        },
    ),
    "strong": WikiMarkSpec(),
    "em": WikiMarkSpec(),
    "strike": WikiMarkSpec(),
    "highlight": WikiMarkSpec(
        attrs={"color": WikiAttrSpec(kind=WikiAttrKind.STRING, default="yellow")}
    ),
    "code": WikiMarkSpec(excludes="_"),
}

MARK_SERIALIZATION_ORDER: Final[tuple[str, ...]] = (
    "link",
    "strong",
    "em",
    "strike",
    "highlight",
    "code",
)
"""Порядок вложенности марок при записи markdown.

Фиксирован, иначе один и тот же документ у разных клиентов даст разный текст,
и каждое сохранение будет выглядеть как изменение содержимого.
"""

BLOCK_NODES_WITHOUT_MARKDOWN: Final[frozenset[str]] = frozenset(
    {"toggle_summary", "table_row", "list_item", "task_item", "table_cell", "table_header"}
)
"""Узлы, которые не имеют собственного markdown-представления и
сериализуются через родителя.

Реестр не декоративный: `tests/wiki/test_wiki_markdown_coverage.py` требует, чтобы
каждый остальной узел схемы имел ветку в сериализаторе. Добавить узел и забыть
про markdown теперь нельзя."""

TABLE_CELL_NODES: Final[frozenset[str]] = frozenset({"table_cell", "table_header"})


class WikiSchemaError(ValueError):
    """Документ не соответствует канонической схеме."""


def _normalize_attr_value(
    node_or_mark: str, attr_name: str, spec: WikiAttrSpec, raw: ProseMirrorAttrValue
) -> ProseMirrorAttrValue:
    """Привести значение атрибута к типу схемы.

    Yjs отдаёт числа как float (`level: 1.0`), поэтому целочисленные атрибуты
    нормализуются явно — иначе схема ProseMirror и markdown разойдутся.
    """
    if raw is None:
        if spec.required:
            raise WikiSchemaError(f"{node_or_mark}.{attr_name}: required attribute is empty")
        return spec.default

    if spec.kind == WikiAttrKind.INT:
        return _normalize_int_attr(node_or_mark, attr_name, raw)

    if spec.kind == WikiAttrKind.INT_LIST:
        if not isinstance(raw, list):
            raise WikiSchemaError(
                f"{node_or_mark}.{attr_name}: expected a list of integers, got {raw!r}"
            )
        return [
            _normalize_int_attr(node_or_mark, f"{attr_name}[{index}]", item)
            for index, item in enumerate(raw)
        ]

    if spec.kind == WikiAttrKind.FLOAT:
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected number")
        return float(raw)

    if spec.kind == WikiAttrKind.BOOL:
        if not isinstance(raw, bool):
            raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected bool")
        return raw

    if not isinstance(raw, str):
        raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected string")
    return raw


def _normalize_int_attr(
    node_or_mark: str, attr_name: str, raw: ProseMirrorAttrValue
) -> int:
    if isinstance(raw, bool):
        raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected integer, got bool")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected integer, got {raw}")
        return int(raw)
    if isinstance(raw, int):
        return raw
    raise WikiSchemaError(f"{node_or_mark}.{attr_name}: expected integer, got {raw!r}")


def _normalize_mark(mark: ProseMirrorMark) -> ProseMirrorMark:
    spec = WIKI_MARKS.get(mark.type)
    if spec is None:
        raise WikiSchemaError(f"Unknown mark: {mark.type}")
    unknown = set(mark.attrs) - set(spec.attrs)
    if unknown:
        raise WikiSchemaError(f"Mark {mark.type}: unknown attributes {sorted(unknown)}")
    attrs: dict[str, ProseMirrorAttrValue] = {}
    for attr_name, attr_spec in spec.attrs.items():
        attrs[attr_name] = _normalize_attr_value(
            mark.type, attr_name, attr_spec, mark.attrs.get(attr_name)
        )
    return ProseMirrorMark(type=mark.type, attrs=attrs)


def normalize_document_in_serialization_order(node: ProseMirrorNode) -> ProseMirrorNode:
    """Проверить документ по схеме и вернуть нормализованную копию.

    Нормализация приводит атрибуты к типам схемы, подставляет их значения по
    умолчанию и упорядочивает марки. Неизвестный узел, марка или атрибут —
    ошибка: тихо отбрасывать содержимое нельзя, это потеря данных пользователя.
    """
    spec = WIKI_NODES.get(node.type)
    if spec is None:
        raise WikiSchemaError(f"Unknown node: {node.type}")

    unknown = set(node.attrs) - set(spec.attrs)
    if unknown:
        raise WikiSchemaError(f"Node {node.type}: unknown attributes {sorted(unknown)}")

    attrs: dict[str, ProseMirrorAttrValue] = {}
    for attr_name, attr_spec in spec.attrs.items():
        attrs[attr_name] = _normalize_attr_value(
            node.type, attr_name, attr_spec, node.attrs.get(attr_name)
        )

    if node.type == HEADING_NODE:
        level = attrs.get("level")
        if not isinstance(level, int) or level < 1 or level > MAX_HEADING_LEVEL:
            raise WikiSchemaError(f"heading.level out of range 1..{MAX_HEADING_LEVEL}: {level}")

    if node.type == MENTION_NODE:
        raw_kind = attrs.get("mention_kind")
        if raw_kind not in {member.value for member in WikiMentionKind}:
            raise WikiSchemaError(f"platform_mention.mention_kind is unknown: {raw_kind!r}")

    if node.type in TABLE_CELL_NODES:
        raw_align = attrs.get("align")
        if raw_align not in {member.value for member in WikiTableAlign}:
            raise WikiSchemaError(f"{node.type}.align is unknown: {raw_align!r}")

    if node.type == TEXT_NODE:
        if node.text is None:
            raise WikiSchemaError("Text node has no text")
        if node.content:
            raise WikiSchemaError("Text node cannot have content")
    elif node.text is not None:
        raise WikiSchemaError(f"Node {node.type} cannot carry text")

    marks = [_normalize_mark(mark) for mark in node.marks]
    if marks and spec.marks == "":
        raise WikiSchemaError(f"Node {node.type} does not allow marks")
    marks.sort(key=lambda mark: MARK_SERIALIZATION_ORDER.index(mark.type))

    return ProseMirrorNode(
        type=node.type,
        attrs=attrs,
        content=[normalize_document_in_serialization_order(child) for child in node.content],
        marks=marks,
        text=node.text,
    )


def _attr_spec_json(spec: WikiAttrSpec) -> JsonObject:
    return {
        "kind": spec.kind.value,
        "default": spec.default,
        "required": spec.required,
    }


def schema_as_json() -> JsonObject:
    """Схема в виде JSON для сборки браузерной схемы ProseMirror."""
    nodes: JsonObject = {}
    for name, spec in WIKI_NODES.items():
        node_json: JsonObject = {
            "group": spec.group,
            "content": spec.content,
            "marks": spec.marks,
            "inline": spec.inline,
            "atom": spec.atom,
            "defining": spec.defining,
            "isolating": spec.isolating,
            "code": spec.code,
            "draggable": spec.draggable,
            "selectable": spec.selectable,
            "attrs": {
                attr_name: _attr_spec_json(attr_spec)
                for attr_name, attr_spec in spec.attrs.items()
            },
        }
        nodes[name] = node_json

    marks: JsonObject = {}
    for name, mark_spec in WIKI_MARKS.items():
        mark_json: JsonObject = {
            "inclusive": mark_spec.inclusive,
            "spanning": mark_spec.spanning,
            "excludes": mark_spec.excludes,
            "attrs": {
                attr_name: _attr_spec_json(attr_spec)
                for attr_name, attr_spec in mark_spec.attrs.items()
            },
        }
        marks[name] = mark_json

    payload: dict[str, JsonValue] = {
        "nodes": nodes,
        "marks": marks,
        "mark_order": list(MARK_SERIALIZATION_ORDER),
        "mention_kinds": [member.value for member in WikiMentionKind],
        "callout_tones": [member.value for member in WikiCalloutTone],
        "table_aligns": [member.value for member in WikiTableAlign],
        "max_heading_level": MAX_HEADING_LEVEL,
    }
    return payload


__all__ = [
    "BLOCK_NODES_WITHOUT_MARKDOWN",
    "DOC_NODE",
    "FILE_NODE",
    "FOOTNOTE_DEFINITION_NODE",
    "FOOTNOTE_REFERENCE_NODE",
    "HEADING_NODE",
    "MARK_SERIALIZATION_ORDER",
    "MATH_BLOCK_NODE",
    "MATH_INLINE_NODE",
    "MAX_HEADING_LEVEL",
    "MENTION_NODE",
    "PARAGRAPH_NODE",
    "TABLE_CELL_NODES",
    "TEXT_NODE",
    "WIKI_MARKS",
    "WIKI_NODES",
    "WikiAttrKind",
    "WikiAttrSpec",
    "WikiCalloutTone",
    "WikiMarkSpec",
    "WikiMentionKind",
    "WikiNodeSpec",
    "WikiSchemaError",
    "WikiTableAlign",
    "normalize_document_in_serialization_order",
    "schema_as_json",
]
