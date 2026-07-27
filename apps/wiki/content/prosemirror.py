"""
Типизированное представление документа ProseMirror.

Поля `type`, `attrs`, `content`, `marks`, `text` заданы спецификацией ProseMirror
и повторяют её имена: это wire-формат внешнего редактора, а не доменная модель
платформы, поэтому голый `type` здесь канонический.

Источник правды содержимого страницы — `ProseMirrorNode`. Markdown выводится
из него сериализатором и никогда не редактируется напрямую.
"""

from __future__ import annotations

from pydantic import Field, field_validator

from apps.wiki.base_model import WikiContentModel

type ProseMirrorAttrValue = str | int | float | bool | None
"""Значение атрибута ноды или марки.

Схема wiki допускает только скаляры: они переживают round-trip через Yjs
и напрямую ложатся в метаданные RAG, где поддерживаются лишь string/number/boolean.
"""


class ProseMirrorMark(WikiContentModel):
    """Марка форматирования на текстовом узле."""

    type: str = Field(..., min_length=1)
    attrs: dict[str, ProseMirrorAttrValue] = Field(default_factory=dict)


class ProseMirrorNode(WikiContentModel):
    """Узел документа ProseMirror.

    Текстовые узлы несут `text` и не имеют `content`; блочные — наоборот.
    """

    type: str = Field(..., min_length=1)
    attrs: dict[str, ProseMirrorAttrValue] = Field(default_factory=dict)
    content: list[ProseMirrorNode] = Field(default_factory=list)
    marks: list[ProseMirrorMark] = Field(default_factory=list)
    text: str | None = None

    @field_validator("text")
    @classmethod
    def _text_only_for_text_nodes(cls, value: str | None) -> str | None:
        if value is not None and value == "":
            raise ValueError("ProseMirror text node не может быть пустой строкой")
        return value


def empty_document() -> ProseMirrorNode:
    """Пустой документ: `doc` с одним пустым параграфом.

    ProseMirror не допускает `doc` без содержимого при `content: "block+"`,
    поэтому пустая страница всегда создаётся с параграфом.
    """
    return ProseMirrorNode(type="doc", content=[ProseMirrorNode(type="paragraph")])


def text_node(value: str, marks: list[ProseMirrorMark] | None = None) -> ProseMirrorNode:
    """Текстовый узел с необязательным набором марок."""
    return ProseMirrorNode(type="text", text=value, marks=marks if marks else [])


def iter_nodes(node: ProseMirrorNode) -> list[ProseMirrorNode]:
    """Обход документа в порядке документа, включая корень."""
    collected: list[ProseMirrorNode] = [node]
    for child in node.content:
        collected.extend(iter_nodes(child))
    return collected


__all__ = [
    "ProseMirrorAttrValue",
    "ProseMirrorMark",
    "ProseMirrorNode",
    "empty_document",
    "iter_nodes",
    "text_node",
]
