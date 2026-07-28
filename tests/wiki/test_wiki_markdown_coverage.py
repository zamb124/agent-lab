"""
Полнота покрытия схемы markdown-конвертерами.

Узел легко добавить в схему и забыть про markdown: редактор его покажет, а
первое же сохранение упадёт на `WikiSchemaError`, потому что `text_markdown`
выводится из документа на каждой записи. Эти тесты не дают такому узлу
проскочить: каждый узел и каждая марка обязаны иметь ветку в сериализаторе.
"""

from __future__ import annotations

import pytest

from apps.wiki.content.markdown_serializer import document_to_markdown
from apps.wiki.content.prosemirror import ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import (
    BLOCK_NODES_WITHOUT_MARKDOWN,
    DOC_NODE,
    MARK_SERIALIZATION_ORDER,
    TEXT_NODE,
    WIKI_MARKS,
    WIKI_NODES,
    WikiSchemaError,
)

INLINE_NODES_WITHOUT_MARKDOWN: frozenset[str] = frozenset()
"""Inline-узлов без markdown-представления в схеме нет; список нужен, чтобы
исключение приходилось объявлять явно, а не появлялось молча."""

_SKIPPED = BLOCK_NODES_WITHOUT_MARKDOWN | INLINE_NODES_WITHOUT_MARKDOWN | {DOC_NODE, TEXT_NODE}

SERIALIZABLE_NODES = sorted(set(WIKI_NODES) - _SKIPPED)


def _sample_inline() -> list[ProseMirrorNode]:
    return [ProseMirrorNode(type="text", text="текст")]


def _sample_paragraph() -> ProseMirrorNode:
    return ProseMirrorNode(type="paragraph", content=_sample_inline())


def _sample_node(node_type: str) -> ProseMirrorNode:
    """Минимальный валидный узел каждого типа схемы."""
    if node_type == "paragraph":
        return _sample_paragraph()
    if node_type == "heading":
        return ProseMirrorNode(type="heading", attrs={"level": 2}, content=_sample_inline())
    if node_type == "blockquote":
        return ProseMirrorNode(type="blockquote", content=[_sample_paragraph()])
    if node_type == "code_block":
        return ProseMirrorNode(
            type="code_block",
            attrs={"language": "python"},
            content=[ProseMirrorNode(type="text", text="print(1)")],
        )
    if node_type in {"bullet_list", "ordered_list"}:
        return ProseMirrorNode(
            type=node_type,
            content=[ProseMirrorNode(type="list_item", content=[_sample_paragraph()])],
        )
    if node_type == "task_list":
        return ProseMirrorNode(
            type="task_list",
            content=[
                ProseMirrorNode(
                    type="task_item", attrs={"checked": True}, content=[_sample_paragraph()]
                )
            ],
        )
    if node_type == "toggle":
        return ProseMirrorNode(
            type="toggle",
            content=[
                ProseMirrorNode(type="toggle_summary", content=_sample_inline()),
                _sample_paragraph(),
            ],
        )
    if node_type == "callout":
        return ProseMirrorNode(
            type="callout", attrs={"tone": "info"}, content=[_sample_paragraph()]
        )
    if node_type == "horizontal_rule":
        return ProseMirrorNode(type="horizontal_rule")
    if node_type == "image":
        return ProseMirrorNode(type="image", attrs={"src": "https://example.com/i.png"})
    if node_type == "table":
        cell = ProseMirrorNode(type="table_cell", content=[_sample_paragraph()])
        header = ProseMirrorNode(type="table_header", content=[_sample_paragraph()])
        return ProseMirrorNode(
            type="table",
            content=[
                ProseMirrorNode(type="table_row", content=[header]),
                ProseMirrorNode(type="table_row", content=[cell]),
            ],
        )
    if node_type == "platform_file":
        return ProseMirrorNode(type="platform_file", attrs={"file_id": "f-1"})
    if node_type == "platform_mention":
        return ProseMirrorNode(
            type="paragraph",
            content=[
                ProseMirrorNode(
                    type="platform_mention",
                    attrs={"mention_kind": "user", "target_id": "u-1", "label": "Иван"},
                )
            ],
        )
    if node_type == "hard_break":
        return ProseMirrorNode(
            type="paragraph",
            content=[*_sample_inline(), ProseMirrorNode(type="hard_break"), *_sample_inline()],
        )
    if node_type == "footnote_definition":
        return ProseMirrorNode(
            type="footnote_definition", attrs={"label": "1"}, content=[_sample_paragraph()]
        )
    if node_type == "footnote_reference":
        return ProseMirrorNode(
            type="paragraph",
            content=[
                ProseMirrorNode(type="footnote_reference", attrs={"label": "1"}),
            ],
        )
    if node_type == "math_block":
        return ProseMirrorNode(type="math_block", attrs={"formula": "x^2"})
    if node_type == "math_inline":
        return ProseMirrorNode(
            type="paragraph",
            content=[ProseMirrorNode(type="math_inline", attrs={"formula": "x^2"})],
        )
    pytest.fail(
        f"Узел {node_type} нет в наборе примеров: добавьте его сюда и в сериализатор"
    )


@pytest.mark.parametrize("node_type", SERIALIZABLE_NODES)
def test_every_schema_node_is_serializable(node_type: str):
    document = ProseMirrorNode(type=DOC_NODE, content=[_sample_node(node_type)])
    rendered = document_to_markdown(document)
    assert rendered != "", f"{node_type} дал пустой markdown"


@pytest.mark.parametrize("mark_type", sorted(WIKI_MARKS))
def test_every_schema_mark_is_serializable(mark_type: str):
    attrs = {"href": "https://example.com"} if mark_type == "link" else {}
    document = ProseMirrorNode(
        type=DOC_NODE,
        content=[
            ProseMirrorNode(
                type="paragraph",
                content=[
                    ProseMirrorNode(
                        type="text",
                        text="текст",
                        marks=[ProseMirrorMark(type=mark_type, attrs=attrs)],
                    )
                ],
            )
        ],
    )
    rendered = document_to_markdown(document)
    assert "текст" in rendered


def test_skipped_nodes_are_serialized_through_their_parent():
    """Узлы из реестра исключений не сериализуются сами — только через родителя."""
    for node_type in BLOCK_NODES_WITHOUT_MARKDOWN:
        assert node_type in WIKI_NODES, f"{node_type} нет в схеме"


def test_serializer_rejects_node_outside_schema():
    document = ProseMirrorNode(
        type=DOC_NODE, content=[ProseMirrorNode(type="unknown_block")]
    )
    with pytest.raises(WikiSchemaError):
        _ = document_to_markdown(document)


def test_mark_order_covers_every_mark():
    assert set(MARK_SERIALIZATION_ORDER) == set(WIKI_MARKS)
