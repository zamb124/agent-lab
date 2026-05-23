from core.docs.assistant import (
    docs_search_card_blocks,
    docs_url_for_page,
    parse_llms_full,
)


def test_parse_llms_full_keeps_page_internal_headings():
    text = """# Документация Humanitec

Описание.

## Первая страница

Source: https://humanitec.ru/documentation/first/

Вступление.

## Внутренний заголовок

Текст внутри первой страницы.

## Вторая страница

Source: https://humanitec.ru/documentation/second/

Текст второй страницы.
"""
    pages = parse_llms_full(text, language="ru")

    assert len(pages) == 2
    assert pages[0].title == "Первая страница"
    assert "Внутренний заголовок" in pages[0].content
    assert pages[0].page_path == "first"
    assert pages[1].title == "Вторая страница"


def test_docs_url_for_page_uses_current_docs_origin_and_language():
    url = docs_url_for_page(
        page_path="api/flows",
        language="en",
        current_page_url="http://lvh.me:8002/documentation/en/quickstart/",
        fallback_url="https://humanitec.ru/documentation/en/api/flows/",
    )

    assert url == "http://lvh.me:8002/documentation/en/api/flows/"


def test_docs_search_card_blocks_build_clickable_cards():
    blocks = docs_search_card_blocks(
        [
            {
                "title": "Flows",
                "url": "http://lvh.me:8002/documentation/flows/",
                "content": "Как создать flow и добавить LLM node.",
            }
        ],
        language="ru",
    )

    assert blocks == [
        {
            "type": "card",
            "title": "Flows",
            "subtitle": "Открыть страницу документации",
            "description": "Как создать flow и добавить LLM node.",
            "url": "http://lvh.me:8002/documentation/flows/",
        }
    ]
