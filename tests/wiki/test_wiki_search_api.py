"""
Поиск по страницам: текстовый слой Postgres и смысловой слой RAG.

Оба канала работают против настоящих движков: полнотекстовый индекс —
generated-колонка `search_vector`, смысловой — реальные эмбеддинги стека.
"""

from __future__ import annotations

import pytest

from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles

SEARCH_URL = f"{API_PREFIX}/search"


async def _search(client, query: str, **extra: object) -> list[dict[str, object]]:
    response = await client.post(SEARCH_URL, json={"query": query, **extra})
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_lexical_search_finds_page_by_body(wiki_client, create_page, unique_id):
    marker = f"инвентаризация{unique_id}"
    page = await create_page(f"Склад {unique_id}", markdown=f"Проводим {marker} ежегодно.")

    items = await _search(wiki_client, marker, mode="lexical")

    assert [item["wiki_page_id"] for item in items] == [page["wiki_page_id"]]
    assert items[0]["channel"] == "lexical"


async def test_lexical_search_finds_page_by_title(wiki_client, create_page, unique_id):
    marker = f"онбординг{unique_id}"
    page = await create_page(f"{marker} новичка", markdown="Общее описание процесса.")

    items = await _search(wiki_client, marker, mode="lexical")

    assert [item["wiki_page_id"] for item in items] == [page["wiki_page_id"]]


async def test_search_returns_empty_for_unknown_term(wiki_client, wiki_page, unique_id):
    items = await _search(wiki_client, f"несуществующее{unique_id}", mode="lexical")

    assert items == []


async def test_search_respects_limit(wiki_client, create_page, unique_id):
    marker = f"повтор{unique_id}"
    for index in range(3):
        _ = await create_page(f"Стр {index} {unique_id}", markdown=f"Текст {marker}.")

    items = await _search(wiki_client, marker, mode="lexical", limit=2)

    assert len(items) == 2


async def test_deleted_page_leaves_search_results(wiki_client, create_page, unique_id):
    marker = f"исчезающий{unique_id}"
    page = await create_page(f"Временная {unique_id}", markdown=f"Текст {marker}.")
    assert await _search(wiki_client, marker, mode="lexical")

    assert (await wiki_client.delete(f"{PAGES_URL}/{page['wiki_page_id']}")).status_code == 204

    assert await _search(wiki_client, marker, mode="lexical") == []


async def test_updated_text_replaces_old_search_terms(wiki_client, create_page, unique_id):
    old_marker = f"старыйтермин{unique_id}"
    new_marker = f"новыйтермин{unique_id}"
    page = await create_page(f"Правимая {unique_id}", markdown=f"Текст {old_marker}.")

    updated = await wiki_client.put(
        f"{PAGES_URL}/{page['wiki_page_id']}/content",
        json={"markdown": f"Текст {new_marker}."},
    )
    assert updated.status_code == 200, updated.text

    assert await _search(wiki_client, old_marker, mode="lexical") == []
    assert [item["wiki_page_id"] for item in await _search(wiki_client, new_marker, mode="lexical")] == [
        page["wiki_page_id"]
    ]


async def test_restricted_page_is_excluded_from_colleague_results(
    wiki_client, wiki_client_member, create_page, unique_id
):
    marker = f"ограниченный{unique_id}"
    page = await create_page(f"Закрытая {unique_id}", markdown=f"Текст {marker}.")
    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    assert await _search(wiki_client_member, marker, mode="lexical") == []
    assert await _search(wiki_client, marker, mode="lexical")


async def test_semantic_search_finds_page_by_meaning(wiki_client, create_page, unique_id):
    page = await create_page(
        f"Отпуск {unique_id}",
        markdown="Сотрудник подаёт заявление на ежегодный оплачиваемый отпуск за две недели.",
    )

    items = await _search(wiki_client, "как оформить отпуск", mode="semantic", limit=10)

    # Смысловой канал работает через реальные эмбеддинги: точного совпадения слов
    # в запросе нет, страница должна найтись по смыслу.
    assert page["wiki_page_id"] in {item["wiki_page_id"] for item in items}
    assert all(item["channel"] == "semantic" for item in items)


async def test_semantic_search_hides_restricted_page_from_colleague(
    wiki_client, wiki_client_member, create_page, unique_id
):
    page = await create_page(
        f"Премии {unique_id}",
        markdown="Порядок начисления квартальной премии сотрудникам отдела продаж.",
    )
    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    items = await _search(wiki_client_member, "начисление премии", mode="semantic", limit=10)

    assert page["wiki_page_id"] not in {item["wiki_page_id"] for item in items}


async def test_semantic_search_finds_own_restricted_page(
    wiki_client, create_page, unique_id
):
    page = await create_page(
        f"Закрытая инструкция {unique_id}",
        markdown="Внутренний регламент согласования бюджета подразделения.",
    )
    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    items = await _search(wiki_client, "согласование бюджета", mode="semantic", limit=10)

    assert page["wiki_page_id"] in {item["wiki_page_id"] for item in items}


async def test_auto_mode_combines_channels_without_duplicates(
    wiki_client, create_page, unique_id
):
    marker = f"комбинированный{unique_id}"
    page = await create_page(f"Смешанная {unique_id}", markdown=f"Текст {marker} для поиска.")

    items = await _search(wiki_client, marker, mode="auto", limit=10)

    found = [item for item in items if item["wiki_page_id"] == page["wiki_page_id"]]
    assert len(found) == 1


async def test_search_filters_by_root_section(wiki_client, create_page, unique_id):
    marker = f"разделмаркер{unique_id}"
    first_root = await create_page(f"Раздел А {unique_id}", markdown=f"Текст {marker}.")
    _ = await create_page(f"Раздел Б {unique_id}", markdown=f"Текст {marker}.")

    items = await _search(
        wiki_client, marker, mode="semantic", root_page_id=first_root["wiki_page_id"], limit=10
    )

    assert {item["wiki_page_id"] for item in items} <= {first_root["wiki_page_id"]}


async def test_search_filters_unpublished_pages(wiki_client, create_page, unique_id):
    marker = f"черновиковый{unique_id}"
    page = await create_page(f"Черновик {unique_id}", markdown=f"Текст {marker}.")
    hidden = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}", json={"is_published": False}
    )
    assert hidden.status_code == 200, hidden.text

    items = await _search(wiki_client, marker, mode="semantic", published_only=True, limit=10)

    assert page["wiki_page_id"] not in {item["wiki_page_id"] for item in items}


async def test_empty_query_is_rejected(wiki_client):
    response = await wiki_client.post(SEARCH_URL, json={"query": ""})

    assert response.status_code == 422
