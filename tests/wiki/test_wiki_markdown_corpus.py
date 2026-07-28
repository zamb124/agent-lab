"""
Корпус реальных markdown-файлов.

Проверяется не побайтовое совпадение с исходником — markdown производен от
документа, и нормализация неизбежна. Проверяется другое: файл импортируется без
исключения, ничего из содержимого не исчезает молча, а повторный проход даёт тот
же текст. Без последнего каждое открытие страницы выглядело бы как правка.
"""

from __future__ import annotations

import pathlib

import pytest

from apps.wiki.content.markdown_file import split_markdown_file
from apps.wiki.content.markdown_notices import WikiMarkdownNoticeKind
from apps.wiki.content.markdown_parser import parse_markdown
from apps.wiki.content.markdown_serializer import document_to_markdown
from apps.wiki.content.prosemirror import ProseMirrorNode, iter_nodes

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "markdown"

CORPUS = sorted(path.name for path in FIXTURES.glob("*.md"))


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _document(name: str) -> ProseMirrorNode:
    parts = split_markdown_file(_read(name))
    return parse_markdown(parts.body).document


@pytest.mark.parametrize("name", CORPUS)
def test_corpus_file_parses_and_is_stable(name: str):
    parts = split_markdown_file(_read(name))
    parsed = parse_markdown(parts.body)

    once = document_to_markdown(parsed.document)
    twice = document_to_markdown(parse_markdown(once).document)
    assert once == twice, f"{name}: повторный проход изменил markdown"


@pytest.mark.parametrize("name", CORPUS)
def test_corpus_file_keeps_its_words(name: str):
    """Слова исходника не должны исчезать: разметка меняется, текст — нет."""
    parts = split_markdown_file(_read(name))
    document = parse_markdown(parts.body).document
    rendered = document_to_markdown(document)

    # Слова из тела, которые обязаны дойти до результата. HTML-теги и служебные
    # символы markdown из сравнения исключены: они и есть разметка.
    for word in ("Заголовок", "абзац", "пункт", "таблице", "цитата"):
        if word in parts.body and word not in rendered:
            pytest.fail(f"{name}: слово {word!r} потерялось при разборе")


def test_gfm_corpus_covers_every_construct():
    document = _document("gfm_full.md")
    types = {node.type for node in iter_nodes(document)}
    assert {
        "heading",
        "paragraph",
        "blockquote",
        "code_block",
        "bullet_list",
        "ordered_list",
        "task_list",
        "toggle",
        "callout",
        "horizontal_rule",
        "image",
        "table",
        "platform_file",
        "platform_mention",
        "hard_break",
        "footnote_definition",
        "footnote_reference",
        "math_block",
        "math_inline",
    } <= types


def test_heading_levels_five_and_six_survive():
    document = _document("gfm_full.md")
    levels = [
        node.attrs["level"] for node in document.content if node.type == "heading"
    ]
    assert 5 in levels
    assert 6 in levels


def test_table_alignment_survives_roundtrip():
    document = _document("gfm_full.md")
    table = next(node for node in document.content if node.type == "table")
    header = table.content[0]
    assert [cell.attrs["align"] for cell in header.content] == [
        "left",
        "center",
        "right",
        "",
    ]
    assert "| :--- | :---: | ---: | --- |" in document_to_markdown(document)


def test_footnote_definitions_move_to_the_end():
    """Определение посреди текста сделало бы markdown невалидным."""
    document = _document("gfm_full.md")
    rendered = document_to_markdown(document)
    lines = rendered.splitlines()
    definition_lines = [
        index for index, line in enumerate(lines) if line.startswith("[^")
    ]
    other_lines = [
        index
        for index, line in enumerate(lines)
        if line.strip() and not line.startswith("[^")
    ]
    assert definition_lines
    assert min(definition_lines) > max(other_lines)


def test_html_whitelist_becomes_schema_nodes():
    document = _document("html_laced.md")
    types = {node.type for node in iter_nodes(document)}
    # <details>/<summary> — сворачиваемый блок, <table> — таблица, <br> — перенос.
    assert {"toggle", "toggle_summary", "table", "hard_break", "image"} <= types
    marks = {
        mark.type for node in iter_nodes(document) for mark in node.marks
    }
    assert {"strong", "em", "code", "highlight", "strike", "link"} <= marks


def test_dangerous_html_never_reaches_the_document():
    parsed = parse_markdown(_read("html_laced.md"))
    rendered = document_to_markdown(parsed.document)
    for forbidden in ("<script", "alert(", "<iframe", "<style", "color: red"):
        assert forbidden not in rendered

    dropped = {
        notice.detail
        for notice in parsed.notices
        if notice.kind is WikiMarkdownNoticeKind.DROPPED_HTML
    }
    assert any("script" in detail for detail in dropped)
    assert any("iframe" in detail for detail in dropped)


def test_unknown_inline_tags_are_reported_not_swallowed():
    parsed = parse_markdown(_read("html_laced.md"))
    kinds = {notice.kind for notice in parsed.notices}
    assert WikiMarkdownNoticeKind.DROPPED_HTML in kinds
    # Текст внутри неизвестного тега остаётся в документе.
    rendered = document_to_markdown(parsed.document)
    assert "Текст в span" in rendered
    assert "верхний индекс" in rendered


def test_relative_page_links_are_reported():
    parsed = parse_markdown(split_markdown_file(_read("obsidian_export.md")).body)
    unresolved = [
        notice
        for notice in parsed.notices
        if notice.kind is WikiMarkdownNoticeKind.UNRESOLVED_PAGE_LINK
    ]
    assert {notice.detail.split()[3] for notice in unresolved} == {
        "./other-note.md",
        "sub/dir/page.markdown",
    }


def test_front_matter_becomes_page_properties():
    parts = split_markdown_file(_read("obsidian_export.md"))
    assert parts.front_matter.title == "Заметка из Obsidian"
    assert parts.front_matter.cover_url == "https://example.com/cover.jpg"
    assert not parts.body.startswith("---")
    # `tags` страницей не используется — о ключе сообщается, а не молчится.
    unknown = [
        notice
        for notice in parts.notices
        if notice.kind is WikiMarkdownNoticeKind.FRONT_MATTER_UNKNOWN_KEY
    ]
    assert [notice.detail for notice in unknown] == [
        "ключ шапки tags страницей не используется"
    ]


def test_inline_image_is_lifted_into_its_own_block():
    parsed = parse_markdown(split_markdown_file(_read("obsidian_export.md")).body)
    assert any(
        notice.kind is WikiMarkdownNoticeKind.IMAGE_EXTRACTED for notice in parsed.notices
    )
    types = [node.type for node in parsed.document.content]
    assert "image" in types
    # Текст вокруг изображения сохранён абзацами по обе стороны.
    image_index = types.index("image")
    assert types[image_index - 1] == "paragraph"
    assert types[image_index + 1] == "paragraph"
