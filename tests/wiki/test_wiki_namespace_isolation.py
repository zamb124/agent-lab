"""
Изоляция по пространству.

Namespace — граница данных, а не фильтр по умолчанию: страницы не видны из
чужого пространства и из чужой компании, а перенос между пространствами
переносит поддерево целиком и явной операцией.
"""

from __future__ import annotations

import pytest

from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


async def test_page_is_invisible_from_another_namespace(
    wiki_page, wiki_client_other_namespace
):
    response = await wiki_client_other_namespace.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}")

    # Именно 404, а не 403: чужое пространство не должно подтверждать,
    # что такая страница вообще существует.
    assert response.status_code == 404


async def test_tree_does_not_leak_between_namespaces(
    wiki_page, wiki_client_other_namespace
):
    response = await wiki_client_other_namespace.get(PAGES_URL)

    assert response.status_code == 200, response.text
    assert wiki_page["wiki_page_id"] not in {
        item["wiki_page_id"] for item in response.json()["items"]
    }


async def test_search_does_not_leak_between_namespaces(
    wiki_client, wiki_client_other_namespace, create_page, unique_id
):
    marker = f"уникальныймаркер{unique_id}"
    _ = await create_page(f"Секрет {unique_id}", markdown=f"Текст {marker} внутри")

    own = await wiki_client.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )
    other = await wiki_client_other_namespace.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )

    assert len(own.json()["items"]) == 1
    assert other.json()["items"] == []


async def test_page_is_invisible_for_another_company(wiki_page, wiki_client_company2):
    response = await wiki_client_company2.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}")

    # Пространство принадлежит компании system — чужая компания получает отказ
    # ещё на проверке границы.
    assert response.status_code in (403, 400)


async def test_update_from_another_namespace_is_rejected(
    wiki_page, wiki_client_other_namespace
):
    response = await wiki_client_other_namespace.put(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/content",
        json={"markdown": "Правка из чужого пространства"},
    )

    assert response.status_code == 404


async def test_delete_from_another_namespace_is_rejected(
    wiki_page, wiki_client_other_namespace
):
    response = await wiki_client_other_namespace.delete(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}"
    )

    assert response.status_code == 404


async def test_move_namespace_transfers_whole_subtree(
    wiki_client,
    wiki_client_other_namespace,
    create_page,
    wiki_other_namespace,
    unique_id,
):
    parent = await create_page(f"Переносимый {unique_id}")
    child = await create_page(f"Потомок {unique_id}", parent_page_id=parent["wiki_page_id"])

    response = await wiki_client.post(
        f"{PAGES_URL}/{parent['wiki_page_id']}/move-namespace",
        json={"target_namespace": wiki_other_namespace},
    )

    assert response.status_code == 200, response.text
    assert response.json()["page"]["namespace"] == wiki_other_namespace

    moved_tree = await wiki_client_other_namespace.get(PAGES_URL)
    moved_ids = {item["wiki_page_id"] for item in moved_tree.json()["items"]}
    assert {parent["wiki_page_id"], child["wiki_page_id"]} <= moved_ids

    source_tree = await wiki_client.get(PAGES_URL)
    source_ids = {item["wiki_page_id"] for item in source_tree.json()["items"]}
    assert parent["wiki_page_id"] not in source_ids
    assert child["wiki_page_id"] not in source_ids


async def test_move_namespace_keeps_content_and_search(
    wiki_client, wiki_client_other_namespace, create_page, wiki_other_namespace, unique_id
):
    marker = f"переносимыймаркер{unique_id}"
    page = await create_page(f"Статья {unique_id}", markdown=f"Тело с {marker}.")

    moved = await wiki_client.post(
        f"{PAGES_URL}/{page['wiki_page_id']}/move-namespace",
        json={"target_namespace": wiki_other_namespace},
    )
    assert moved.status_code == 200, moved.text

    read = await wiki_client_other_namespace.get(f"{PAGES_URL}/{page['wiki_page_id']}/markdown")
    assert read.status_code == 200
    assert marker in read.json()["markdown"]

    found = await wiki_client_other_namespace.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )
    assert {item["wiki_page_id"] for item in found.json()["items"]} == {page["wiki_page_id"]}

    gone = await wiki_client.post(
        f"{API_PREFIX}/search", json={"query": marker, "mode": "lexical"}
    )
    assert gone.json()["items"] == []


async def test_move_namespace_to_same_space_is_rejected(
    wiki_client, wiki_page, wiki_namespace
):
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/move-namespace",
        json={"target_namespace": wiki_namespace},
    )

    assert response.status_code == 400


async def test_move_namespace_to_unknown_space_is_rejected(wiki_client, wiki_page):
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/move-namespace",
        json={"target_namespace": "space-that-does-not-exist"},
    )

    assert response.status_code == 400


async def test_same_titles_coexist_in_different_namespaces(
    wiki_client, wiki_client_other_namespace, unique_id
):
    title = f"Одноимённая {unique_id}"

    first = await wiki_client.post(PAGES_URL, json={"title": title, "markdown": "Первая"})
    second = await wiki_client_other_namespace.post(
        PAGES_URL, json={"title": title, "markdown": "Вторая"}
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["page"]["wiki_page_id"] != second.json()["page"]["wiki_page_id"]


async def test_child_creation_across_namespaces_is_rejected(
    wiki_client_other_namespace, wiki_page, unique_id
):
    response = await wiki_client_other_namespace.post(
        PAGES_URL,
        json={"title": f"Чужой ребёнок {unique_id}", "parent_page_id": wiki_page["wiki_page_id"]},
    )

    assert response.status_code == 404
