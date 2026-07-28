"""
Контент-пайплайн wiki: markdown ↔ документ.

Markdown производен от документа, поэтому проверяется не побайтовое равенство
с исходным текстом, а устойчивость: повторный проход не меняет результат.
Иначе каждое открытие страницы выглядело бы как правка.
"""

from __future__ import annotations

import pytest

from apps.wiki.content.markdown_html import html_fragment_to_blocks
from apps.wiki.content.markdown_notices import WikiMarkdownNoticeKind
from apps.wiki.content.markdown_parser import (
    WikiMarkdownError,
    markdown_to_document,
    parse_markdown,
)
from apps.wiki.content.markdown_serializer import (
    document_to_markdown,
    document_to_plain_text,
)
from apps.wiki.content.prosemirror import ProseMirrorMark, ProseMirrorNode
from apps.wiki.content.schema import WikiSchemaError, normalize_document

FULL_DOCUMENT = """# Заголовок

Текст с **жирным**, *курсивом*, ~~зачёркнутым~~, ==подсветкой== и `кодом`. Конец.

## Раздел

- первый
- второй

1. раз
2. два

* [ ] не сделано
* [x] сделано

> Обычная цитата

> [!WARNING]
>
> Осторожно

> [!TOGGLE] Подробности
>
> Скрытый текст

```python
print("hi")
```

| A | B |
| --- | --- |
| 1 | 2 |

---

Ссылка [сюда](https://example.com) и @[Иван](user:u-1), @[Фирма](entity:e-9).

[отчёт.docx](platform-file:f-42)

![картинка](https://example.com/i.png)"""


def _roundtrip(markdown: str) -> str:
    return document_to_markdown(markdown_to_document(markdown))


def test_full_document_roundtrip_is_stable():
    once = _roundtrip(FULL_DOCUMENT)
    twice = _roundtrip(once)
    assert once == twice


def test_block_types_survive_roundtrip():
    document = markdown_to_document(FULL_DOCUMENT)
    types = [node.type for node in document.content]
    assert types == [
        "heading",
        "paragraph",
        "heading",
        "bullet_list",
        "ordered_list",
        "task_list",
        "blockquote",
        "callout",
        "toggle",
        "code_block",
        "table",
        "horizontal_rule",
        "paragraph",
        "platform_file",
        "image",
    ]


def test_callout_keeps_tone_and_body():
    document = markdown_to_document("> [!WARNING]\n>\n> Осторожно")
    callout = document.content[0]
    assert callout.type == "callout"
    assert callout.attrs["tone"] == "warning"
    assert callout.content[0].type == "paragraph"


def test_toggle_separates_summary_from_body():
    document = markdown_to_document("> [!TOGGLE] Итоги\n>\n> Тело блока")
    toggle = document.content[0]
    assert toggle.type == "toggle"
    assert toggle.content[0].type == "toggle_summary"
    summary_text = toggle.content[0].content[0].text
    assert summary_text == "Итоги"
    assert toggle.content[1].type == "paragraph"


def test_task_list_reads_checked_state():
    document = markdown_to_document("* [ ] раз\n* [x] два")
    task_list = document.content[0]
    assert task_list.type == "task_list"
    assert [item.attrs["checked"] for item in task_list.content] == [False, True]


def test_fenced_code_keeps_language():
    document = markdown_to_document('```json\n{"a": 1}\n```')
    block = document.content[0]
    assert block.type == "code_block"
    assert block.attrs["language"] == "json"
    assert block.content[0].text == '{"a": 1}'


def test_fenced_code_normalizes_js_alias():
    document = markdown_to_document("```js\nconst x = 1;\n```")
    assert document.content[0].attrs["language"] == "javascript"


def test_html_pre_code_reads_language_class():
    blocks, notices = html_fragment_to_blocks(
        '<pre><code class="language-json">{"ok": true}</code></pre>'
    )
    assert notices == []
    assert len(blocks) == 1
    assert blocks[0].type == "code_block"
    assert blocks[0].attrs["language"] == "json"
    assert blocks[0].content[0].text == '{"ok": true}'


def test_mentions_become_typed_nodes():
    document = markdown_to_document("Привет @[Иван](user:u-1) и @[Фирма](entity:e-9)")
    mentions = [node for node in document.content[0].content if node.type == "platform_mention"]
    assert [(m.attrs["mention_kind"], m.attrs["target_id"]) for m in mentions] == [
        ("user", "u-1"),
        ("crm_entity", "e-9"),
    ]


def test_standalone_platform_file_link_becomes_block():
    document = markdown_to_document("[смета.xlsx](platform-file:f-7)")
    node = document.content[0]
    assert node.type == "platform_file"
    assert node.attrs["file_id"] == "f-7"
    assert node.attrs["original_name"] == "смета.xlsx"


def test_inline_link_stays_a_mark():
    document = markdown_to_document("см. [доки](https://example.com/a)")
    text_nodes = [n for n in document.content[0].content if n.type == "text"]
    linked = [n for n in text_nodes if any(m.type == "link" for m in n.marks)]
    assert len(linked) == 1
    assert linked[0].marks[0].attrs["href"] == "https://example.com/a"


def test_yjs_float_attributes_are_normalized_to_int():
    # Yjs отдаёт числовые атрибуты как float; схема ProseMirror ждёт int.
    raw = ProseMirrorNode(
        type="doc",
        content=[
            ProseMirrorNode(
                type="heading",
                attrs={"level": 2.0},
                content=[ProseMirrorNode(type="text", text="Заголовок")],
            )
        ],
    )
    normalized = normalize_document(raw)
    assert normalized.content[0].attrs["level"] == 2
    assert document_to_markdown(raw) == "## Заголовок"


def test_table_colwidth_list_is_accepted_and_normalized():
    # Resize колонок пишет colwidth как number[]; Yjs может отдать float в элементах.
    paragraph = ProseMirrorNode(
        type="paragraph", content=[ProseMirrorNode(type="text", text="ячейка")]
    )
    raw = ProseMirrorNode(
        type="doc",
        content=[
            ProseMirrorNode(
                type="table",
                content=[
                    ProseMirrorNode(
                        type="table_row",
                        content=[
                            ProseMirrorNode(
                                type="table_header",
                                attrs={"colwidth": [404.0]},
                                content=[paragraph],
                            ),
                            ProseMirrorNode(
                                type="table_cell",
                                attrs={"colwidth": [220]},
                                content=[paragraph],
                            ),
                        ],
                    )
                ],
            )
        ],
    )
    normalized = normalize_document(raw)
    header = normalized.content[0].content[0].content[0]
    cell = normalized.content[0].content[0].content[1]
    assert header.attrs["colwidth"] == [404]
    assert cell.attrs["colwidth"] == [220]


def test_mark_order_is_deterministic():
    marks_forward = [ProseMirrorMark(type="strong"), ProseMirrorMark(type="em")]
    marks_reversed = [ProseMirrorMark(type="em"), ProseMirrorMark(type="strong")]

    def build(marks: list[ProseMirrorMark]) -> ProseMirrorNode:
        return ProseMirrorNode(
            type="doc",
            content=[
                ProseMirrorNode(
                    type="paragraph",
                    content=[ProseMirrorNode(type="text", text="слово", marks=marks)],
                )
            ],
        )

    assert document_to_markdown(build(marks_forward)) == document_to_markdown(
        build(marks_reversed)
    )


def test_plain_text_drops_markup_but_keeps_mention_labels():
    document = markdown_to_document("# Тема\n\n**жирно** и @[Иван](user:u-1)")
    plain = document_to_plain_text(document)
    assert "**" not in plain
    assert "Тема" in plain
    assert "Иван" in plain


def test_paragraph_starting_like_block_is_escaped():
    document = ProseMirrorNode(
        type="doc",
        content=[
            ProseMirrorNode(
                type="paragraph",
                content=[ProseMirrorNode(type="text", text="- не список, а текст")],
            )
        ],
    )
    rendered = document_to_markdown(document)
    assert rendered.startswith("\\-")
    assert markdown_to_document(rendered).content[0].type == "paragraph"


def test_unknown_node_is_rejected():
    document = ProseMirrorNode(
        type="doc", content=[ProseMirrorNode(type="mystery_block")]
    )
    with pytest.raises(WikiSchemaError):
        _ = normalize_document(document)


def test_raw_html_is_converted_and_reported_not_rejected():
    """Файл с HTML импортируется: отклонить его целиком значит не дать работать.

    Обёртка разворачивается, текст остаётся, о расхождении сообщает заметка.
    """
    result = parse_markdown("<div>сырой html</div>")
    assert document_to_plain_text(result.document) == "сырой html"
    assert [notice.kind for notice in result.notices] == [
        WikiMarkdownNoticeKind.DROPPED_HTML
    ]


def test_mention_without_target_still_raises():
    """Терпимость не безгранична: упоминание без цели — сломанные данные."""
    with pytest.raises(WikiMarkdownError):
        _ = markdown_to_document("@[Иван](user:)")


def test_heading_levels_up_to_six_are_kept():
    document = markdown_to_document("##### Пятый\n\n###### Шестой")
    assert [node.attrs["level"] for node in document.content] == [5, 6]
    assert _roundtrip("##### Пятый") == "##### Пятый"


def test_table_alignment_is_read_and_written():
    document = markdown_to_document("| a | b |\n| :-- | --: |\n| 1 | 2 |")
    header = document.content[0].content[0]
    assert [cell.attrs["align"] for cell in header.content] == ["left", "right"]
    assert "| :--- | ---: |" in document_to_markdown(document)


def test_math_survives_in_both_forms():
    document = markdown_to_document("Формула $x^2$ в тексте.\n\n$$\ny = kx\n$$")
    paragraph = document.content[0]
    assert [node.type for node in paragraph.content if node.type == "math_inline"]
    assert document.content[1].type == "math_block"
    assert document.content[1].attrs["formula"] == "y = kx"
    assert _roundtrip("$$\ny = kx\n$$") == "$$\ny = kx\n$$"


def test_footnote_reference_and_definition_pair_up():
    document = markdown_to_document("Текст[^a].\n\n[^a]: Сноска.")
    reference = next(
        node for node in document.content[0].content if node.type == "footnote_reference"
    )
    definition = next(
        node for node in document.content if node.type == "footnote_definition"
    )
    assert reference.attrs["label"] == definition.attrs["label"] == "a"
    assert _roundtrip("Текст[^a].\n\n[^a]: Сноска.") == "Текст[^a].\n\n[^a]: Сноска."


def test_bare_url_becomes_a_link():
    document = markdown_to_document("Смотри https://example.com/x подробнее.")
    linked = [
        node
        for node in document.content[0].content
        if any(mark.type == "link" for mark in node.marks)
    ]
    assert [node.text for node in linked] == ["https://example.com/x"]


def test_dollar_sign_in_text_is_escaped():
    """Иначе `цена 5$ и 3$` при обратном разборе стало бы формулой."""
    document = ProseMirrorNode(
        type="doc",
        content=[
            ProseMirrorNode(
                type="paragraph",
                content=[ProseMirrorNode(type="text", text="цена 5$ и 3$ за штуку")],
            )
        ],
    )
    rendered = document_to_markdown(document)
    assert rendered == "цена 5\\$ и 3\\$ за штуку"
    assert document_to_plain_text(markdown_to_document(rendered)) == "цена 5$ и 3$ за штуку"
