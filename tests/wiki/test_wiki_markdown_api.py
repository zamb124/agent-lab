"""
Импорт и экспорт markdown через HTTP API.

Путь продовый: реальный сервис, реальная БД, реальная индексация. Проверяется и
ответ, и состояние страницы — иначе тест закрепил бы форму JSON, а не перенос
содержимого.
"""

from __future__ import annotations

import pytest

from tests.wiki.conftest import PAGES_URL

pytestmark = pytest.mark.no_test_doubles

FILE_WITH_FRONT_MATTER = """---
title: Из файла
icon: 📘
cover_url: https://example.com/cover.png
project: неизвестный ключ
---

# Раздел

Абзац с **разметкой** и сноской[^a].

| Лево | Право |
| :--- | ----: |
| 1 | 2 |

[^a]: Пояснение.
"""


async def test_import_creates_page_from_file(wiki_client, stored_page):
    response = await wiki_client.post(
        f"{PAGES_URL}/import/markdown", json={"markdown": FILE_WITH_FRONT_MATTER}
    )

    assert response.status_code == 201, response.text
    body = response.json()
    page = body["page"]
    assert page["title"] == "Из файла"
    assert page["icon"] == "📘"
    assert page["cover_url"] == "https://example.com/cover.png"

    saved = await stored_page(page["wiki_page_id"])
    types = [node.type for node in saved.content.content]
    assert types == ["heading", "paragraph", "table", "footnote_definition"]
    # Шапка в содержимое не попадает: свойства живут в колонках страницы.
    assert not saved.text_markdown.startswith("---")


async def test_import_reports_unknown_front_matter_key(wiki_client):
    response = await wiki_client.post(
        f"{PAGES_URL}/import/markdown", json={"markdown": FILE_WITH_FRONT_MATTER}
    )

    kinds = [notice["kind"] for notice in response.json()["notices"]]
    assert kinds == ["front_matter_unknown_key"]


async def test_import_can_ignore_front_matter(wiki_client):
    response = await wiki_client.post(
        f"{PAGES_URL}/import/markdown",
        json={"markdown": FILE_WITH_FRONT_MATTER, "apply_front_matter": False},
    )

    page = response.json()["page"]
    assert page["title"] == ""
    assert page["icon"] == ""


async def test_import_into_existing_page_replaces_content(
    wiki_client, create_page, stored_page, unique_id
):
    page = await create_page(f"Старое {unique_id}")
    response = await wiki_client.post(
        f"{PAGES_URL}/{page['wiki_page_id']}/import/markdown",
        json={"markdown": "# Новое содержимое\n\nВторой абзац."},
    )

    assert response.status_code == 200, response.text
    saved = await stored_page(page["wiki_page_id"])
    assert saved.text_markdown == "# Новое содержимое\n\nВторой абзац."
    assert saved.revision_count == 1


async def test_import_of_html_file_returns_notices(wiki_client, create_page, unique_id):
    page = await create_page(f"HTML {unique_id}")
    response = await wiki_client.post(
        f"{PAGES_URL}/{page['wiki_page_id']}/import/markdown",
        json={"markdown": "<div>текст</div>\n\n<script>alert(1)</script>"},
    )

    assert response.status_code == 200, response.text
    kinds = {notice["kind"] for notice in response.json()["notices"]}
    assert kinds == {"dropped_html"}
    assert "alert(1)" not in response.json()["page"]["text_markdown"]


async def test_import_rejects_broken_mention(wiki_client, create_page, unique_id):
    page = await create_page(f"Битое {unique_id}")
    response = await wiki_client.post(
        f"{PAGES_URL}/{page['wiki_page_id']}/import/markdown",
        json={"markdown": "@[Иван](user:)"},
    )

    assert response.status_code == 400


async def test_export_file_carries_front_matter_and_body(wiki_client, create_page, unique_id):
    created = await wiki_client.post(
        PAGES_URL,
        json={
            "title": f"Экспорт {unique_id}",
            "icon": "📗",
            "markdown": "# Раздел\n\nТекст.",
        },
    )
    page_id = created.json()["page"]["wiki_page_id"]

    response = await wiki_client.get(f"{PAGES_URL}/{page_id}/markdown/file")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    assert "attachment" in response.headers["content-disposition"]
    text = response.text
    assert text.startswith("---\n")
    assert f"title: Экспорт {unique_id}" in text
    assert "icon: 📗" in text
    assert "# Раздел" in text


async def test_export_file_reimports_into_the_same_page(wiki_client, unique_id, stored_page):
    created = await wiki_client.post(
        PAGES_URL,
        json={
            "title": f"Круг {unique_id}",
            "icon": "📕",
            "markdown": "## Заголовок\n\n- один\n- два\n\n$$\nx^2\n$$",
        },
    )
    source_id = created.json()["page"]["wiki_page_id"]
    exported = await wiki_client.get(f"{PAGES_URL}/{source_id}/markdown/file")

    imported = await wiki_client.post(
        f"{PAGES_URL}/import/markdown", json={"markdown": exported.text}
    )

    assert imported.status_code == 201, imported.text
    assert imported.json()["notices"] == []
    copy = imported.json()["page"]
    assert copy["title"] == f"Круг {unique_id}"
    assert copy["icon"] == "📕"
    source = await stored_page(source_id)
    assert copy["text_markdown"] == source.text_markdown


async def test_json_markdown_route_stays_without_front_matter(wiki_client, unique_id):
    created = await wiki_client.post(
        PAGES_URL, json={"title": f"Агенту {unique_id}", "markdown": "Текст."}
    )
    page_id = created.json()["page"]["wiki_page_id"]

    response = await wiki_client.get(f"{PAGES_URL}/{page_id}/markdown")

    assert response.json()["markdown"] == "Текст."


async def test_parse_route_returns_document_without_saving(wiki_client, create_page, unique_id):
    page = await create_page(f"Нетронутая {unique_id}")

    response = await wiki_client.post(
        f"{PAGES_URL}/markdown/parse", json={"markdown": "# Вставка\n\n<div>текст</div>"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert [node["type"] for node in body["document"]["content"]] == [
        "heading",
        "paragraph",
    ]
    assert [notice["kind"] for notice in body["notices"]] == ["dropped_html"]

    untouched = await wiki_client.get(f"{PAGES_URL}/{page['wiki_page_id']}")
    assert untouched.json()["page"]["text_markdown"] == ""
