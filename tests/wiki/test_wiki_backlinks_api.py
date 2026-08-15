"""
Обратные ссылки: связь видна с обеих сторон.

Ссылки пересчитываются из содержимого при каждом сохранении, поэтому
проверяется и появление связи, и её исчезновение после правки текста.
"""

from __future__ import annotations

import pytest

from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


async def _backlinks(client, target_kind: str, target_id: str) -> list[dict[str, object]]:
    response = await client.get(
        f"{API_PREFIX}/backlinks", params={"target_kind": target_kind, "target_id": target_id}
    )
    assert response.status_code == 200, response.text
    return response.json()["items"]


async def test_crm_mention_creates_backlink(wiki_client, create_page, unique_id):
    entity_id = f"ent-{unique_id}"
    page = await create_page(
        f"Заметка о клиенте {unique_id}",
        markdown=f"Обсудили с @[Клиент](entity:{entity_id}) условия.",
    )

    items = await _backlinks(wiki_client, "crm_entity", entity_id)

    assert [item["wiki_page_id"] for item in items] == [page["wiki_page_id"]]
    assert items[0]["url"] == f"/wiki/p/{page['wiki_page_id']}"


async def test_file_card_creates_backlink(wiki_client, create_page, unique_id):
    file_id = f"file-{unique_id}"
    page = await create_page(
        f"Документация {unique_id}", markdown=f"[смета.xlsx](platform-file:{file_id})"
    )

    items = await _backlinks(wiki_client, "file", file_id)

    assert [item["wiki_page_id"] for item in items] == [page["wiki_page_id"]]


async def test_page_link_creates_backlink(wiki_client, create_page, unique_id):
    target = await create_page(f"Цель {unique_id}")
    source = await create_page(
        f"Источник {unique_id}",
        markdown=f"См. @[Цель](wiki:{target['wiki_page_id']}) подробнее.",
    )

    items = await _backlinks(wiki_client, "wiki_page", target["wiki_page_id"])

    assert [item["wiki_page_id"] for item in items] == [source["wiki_page_id"]]


async def test_several_pages_link_to_same_entity(wiki_client, create_page, unique_id):
    entity_id = f"ent-multi-{unique_id}"
    first = await create_page(f"Первая {unique_id}", markdown=f"@[К](entity:{entity_id})")
    second = await create_page(f"Вторая {unique_id}", markdown=f"@[К](entity:{entity_id})")

    items = await _backlinks(wiki_client, "crm_entity", entity_id)

    assert {item["wiki_page_id"] for item in items} == {
        first["wiki_page_id"],
        second["wiki_page_id"],
    }


async def test_removing_mention_removes_backlink(wiki_client, create_page, unique_id):
    entity_id = f"ent-drop-{unique_id}"
    page = await create_page(f"Черновик {unique_id}", markdown=f"@[К](entity:{entity_id})")
    assert await _backlinks(wiki_client, "crm_entity", entity_id)

    updated = await wiki_client.put(
        f"{PAGES_URL}/{page['wiki_page_id']}/content",
        json={"markdown": "Упоминание убрали."},
    )
    assert updated.status_code == 200, updated.text

    # Набор ссылок переписывается целиком: иначе карточка сущности показывала бы
    # связь, которой в тексте уже нет.
    assert await _backlinks(wiki_client, "crm_entity", entity_id) == []


async def test_duplicate_mentions_produce_single_backlink(wiki_client, create_page, unique_id):
    entity_id = f"ent-dup-{unique_id}"
    _ = await create_page(
        f"Повторы {unique_id}",
        markdown=f"@[К](entity:{entity_id}) и снова @[К](entity:{entity_id})",
    )

    items = await _backlinks(wiki_client, "crm_entity", entity_id)

    assert len(items) == 1


async def test_deleted_page_disappears_from_backlinks(wiki_client, create_page, unique_id):
    entity_id = f"ent-del-{unique_id}"
    page = await create_page(f"Удаляемая {unique_id}", markdown=f"@[К](entity:{entity_id})")

    assert (await wiki_client.delete(f"{PAGES_URL}/{page['wiki_page_id']}")).status_code == 204

    assert await _backlinks(wiki_client, "crm_entity", entity_id) == []


async def test_backlinks_span_namespaces_of_same_company(
    wiki_client, wiki_client_other_namespace, create_page, unique_id
):
    entity_id = f"ent-cross-{unique_id}"
    first = await create_page(f"Из первого {unique_id}", markdown=f"@[К](entity:{entity_id})")
    second_response = await wiki_client_other_namespace.post(
        PAGES_URL,
        json={"title": f"Из второго {unique_id}", "markdown": f"@[К](entity:{entity_id})"},
    )
    assert second_response.status_code == 201, second_response.text
    second = second_response.json()["page"]

    items = await _backlinks(wiki_client, "crm_entity", entity_id)

    # Карточка сущности в Networkle собирает связи из всех пространств компании.
    assert {item["wiki_page_id"] for item in items} == {
        first["wiki_page_id"],
        second["wiki_page_id"],
    }


async def test_restricted_page_is_hidden_from_colleague_backlinks(
    wiki_client, wiki_client_member, create_page, unique_id
):
    entity_id = f"ent-secret-{unique_id}"
    page = await create_page(f"Закрытая {unique_id}", markdown=f"@[К](entity:{entity_id})")

    assert await _backlinks(wiki_client_member, "crm_entity", entity_id)

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )

    assert await _backlinks(wiki_client_member, "crm_entity", entity_id) == []


async def test_backlinks_of_unknown_target_are_empty(wiki_client, unique_id):
    assert await _backlinks(wiki_client, "crm_entity", f"nothing-{unique_id}") == []


async def test_backlinks_require_authentication(wiki_client_anonymous, unique_id):
    response = await wiki_client_anonymous.get(
        f"{API_PREFIX}/backlinks",
        params={"target_kind": "crm_entity", "target_id": f"x-{unique_id}"},
    )

    assert response.status_code in (401, 403)
