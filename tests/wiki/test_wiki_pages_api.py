"""
Жизненный цикл страницы через HTTP API.

Всё идёт по продовому пути: реальный сервис, реальная БД, реальная
индексация. После каждой записи проверяется не только ответ, но и состояние
домена — иначе тест зафиксировал бы форму JSON, а не сохранение.
"""

from __future__ import annotations

import pytest

from core.authz.models import AuthzObject
from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


async def test_create_page_returns_document_and_persists_markdown(wiki_client, stored_page):
    response = await wiki_client.post(
        PAGES_URL,
        json={"title": "Регламент", "markdown": "# Регламент\n\nПервый абзац."},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    page = body["page"]
    assert page["title"] == "Регламент"
    assert page["parent_page_id"] is None
    assert page["root_page_id"] == page["wiki_page_id"]
    assert page["depth"] == 0
    assert page["company_visible"] is True
    assert body["can_edit"] is True

    saved = await stored_page(page["wiki_page_id"])
    assert saved.text_markdown == "# Регламент\n\nПервый абзац."
    assert saved.content.content[0].type == "heading"


async def test_create_page_accepts_prosemirror_content(wiki_client, stored_page):
    content = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Из редактора"}]}
        ],
    }

    response = await wiki_client.post(PAGES_URL, json={"title": "Из PM", "content": content})

    assert response.status_code == 201, response.text
    page_id = response.json()["page"]["wiki_page_id"]
    saved = await stored_page(page_id)
    assert saved.text_markdown == "Из редактора"


async def test_create_page_rejects_both_content_and_markdown(wiki_client):
    response = await wiki_client.post(
        PAGES_URL,
        json={
            "title": "Спор",
            "markdown": "текст",
            "content": {"type": "doc", "content": [{"type": "paragraph"}]},
        },
    )

    assert response.status_code == 400
    assert "markdown" in response.json()["detail"]


async def test_create_page_converts_raw_html_instead_of_failing(wiki_client):
    """Создание по markdown с HTML не отклоняется: тег разворачивается в текст.

    Отклонять весь файл из-за `<div>` значило бы, что импорт настоящих выгрузок
    невозможен; о расхождении сообщает отчёт роутов импорта.
    """
    response = await wiki_client.post(
        PAGES_URL, json={"title": "Сырой html", "markdown": "<div>блок</div>"}
    )

    assert response.status_code == 201
    assert response.json()["page"]["text_markdown"] == "блок"


async def test_create_page_rejects_markdown_with_broken_mention(wiki_client):
    response = await wiki_client.post(
        PAGES_URL, json={"title": "Битое упоминание", "markdown": "@[Иван](user:)"}
    )

    assert response.status_code == 400


async def test_child_page_inherits_root_and_depth(wiki_client, create_page, unique_id):
    parent = await create_page(f"Родитель {unique_id}")
    child = await create_page(f"Ребёнок {unique_id}", parent_page_id=parent["wiki_page_id"])

    assert child["parent_page_id"] == parent["wiki_page_id"]
    assert child["root_page_id"] == parent["wiki_page_id"]
    assert child["depth"] == 1


async def test_tree_lists_pages_with_children_flag(wiki_client, create_page, unique_id):
    parent = await create_page(f"Раздел {unique_id}")
    child = await create_page(f"Статья {unique_id}", parent_page_id=parent["wiki_page_id"])

    response = await wiki_client.get(PAGES_URL)

    assert response.status_code == 200, response.text
    by_id = {item["wiki_page_id"]: item for item in response.json()["items"]}
    assert by_id[parent["wiki_page_id"]]["has_children"] is True
    assert by_id[child["wiki_page_id"]]["has_children"] is False
    assert "content" not in by_id[child["wiki_page_id"]]


async def test_get_page_returns_content_and_permissions(wiki_client, wiki_page):
    response = await wiki_client.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page"]["wiki_page_id"] == wiki_page["wiki_page_id"]
    assert body["page"]["content"]["type"] == "doc"
    assert body["can_edit"] is True
    assert body["can_admin"] is True


async def test_get_missing_page_returns_404(wiki_client):
    response = await wiki_client.get(f"{PAGES_URL}/wpg_missing")

    assert response.status_code == 404


async def test_update_content_creates_revision_and_rewrites_markdown(
    wiki_client, wiki_page, stored_page
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.put(
        f"{PAGES_URL}/{page_id}/content",
        json={"markdown": "## Новый текст\n\nОбновление.", "title": "Обновлено"},
    )

    assert response.status_code == 200, response.text
    put_body = response.json()
    assert put_body["can_edit"] is True
    assert put_body["can_admin"] is True
    saved = await stored_page(page_id)
    assert saved.title == "Обновлено"
    assert saved.text_markdown == "## Новый текст\n\nОбновление."
    assert saved.revision_count == 1

    revisions = await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions")
    assert revisions.status_code == 200
    assert len(revisions.json()["items"]) == 1


async def test_update_content_without_body_is_rejected(wiki_client, wiki_page):
    response = await wiki_client.put(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/content", json={"title": "Только имя"}
    )

    assert response.status_code == 400


async def test_patch_properties_updates_icon_and_publication(wiki_client, wiki_page, stored_page):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}", json={"icon": "book", "is_published": False}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["can_edit"] is True
    assert body["can_admin"] is True
    saved = await stored_page(page_id)
    assert saved.icon == "book"
    assert saved.is_published is False
    # Правка свойств не должна плодить версии содержимого.
    assert saved.revision_count == 0


async def test_patch_properties_switches_full_width(wiki_client, wiki_page, stored_page):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.patch(f"{PAGES_URL}/{page_id}", json={"is_full_width": True})

    assert response.status_code == 200, response.text
    assert response.json()["page"]["is_full_width"] is True
    saved = await stored_page(page_id)
    assert saved.is_full_width is True

    back = await wiki_client.patch(f"{PAGES_URL}/{page_id}", json={"is_full_width": False})

    assert back.status_code == 200, back.text
    restored = await stored_page(page_id)
    assert restored.is_full_width is False


async def test_markdown_endpoint_returns_derived_text(wiki_client, wiki_page):
    response = await wiki_client.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}/markdown")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["wiki_page_id"] == wiki_page["wiki_page_id"]
    assert body["markdown"].startswith("# Заголовок")


async def test_move_page_reparents_and_recomputes_depth(wiki_client, create_page, unique_id):
    first_root = await create_page(f"Первый {unique_id}")
    second_root = await create_page(f"Второй {unique_id}")
    child = await create_page(f"Ребёнок {unique_id}", parent_page_id=first_root["wiki_page_id"])

    response = await wiki_client.post(
        f"{PAGES_URL}/{child['wiki_page_id']}/move",
        json={"parent_page_id": second_root["wiki_page_id"]},
    )

    assert response.status_code == 200, response.text
    moved = response.json()["page"]
    assert moved["parent_page_id"] == second_root["wiki_page_id"]
    assert moved["root_page_id"] == second_root["wiki_page_id"]
    assert moved["depth"] == 1


async def test_move_page_into_own_subtree_is_rejected(wiki_client, create_page, unique_id):
    parent = await create_page(f"Узел {unique_id}")
    child = await create_page(f"Потомок {unique_id}", parent_page_id=parent["wiki_page_id"])

    response = await wiki_client.post(
        f"{PAGES_URL}/{parent['wiki_page_id']}/move",
        json={"parent_page_id": child["wiki_page_id"]},
    )

    assert response.status_code == 400


async def test_move_page_to_root_clears_parent(wiki_client, create_page, unique_id):
    parent = await create_page(f"Верх {unique_id}")
    child = await create_page(f"Низ {unique_id}", parent_page_id=parent["wiki_page_id"])

    response = await wiki_client.post(
        f"{PAGES_URL}/{child['wiki_page_id']}/move", json={"parent_page_id": None}
    )

    assert response.status_code == 200, response.text
    moved = response.json()["page"]
    assert moved["parent_page_id"] is None
    assert moved["depth"] == 0
    assert moved["root_page_id"] == moved["wiki_page_id"]


async def test_delete_page_removes_subtree_from_tree(wiki_client, create_page, unique_id):
    parent = await create_page(f"Удаляемый {unique_id}")
    child = await create_page(f"Потомок {unique_id}", parent_page_id=parent["wiki_page_id"])

    response = await wiki_client.delete(f"{PAGES_URL}/{parent['wiki_page_id']}")
    assert response.status_code == 204

    tree = await wiki_client.get(PAGES_URL)
    remaining = {item["wiki_page_id"] for item in tree.json()["items"]}
    assert parent["wiki_page_id"] not in remaining
    assert child["wiki_page_id"] not in remaining

    deleted = await wiki_client.get(f"{PAGES_URL}/deleted")
    trashed = {item["wiki_page_id"] for item in deleted.json()["items"]}
    assert {parent["wiki_page_id"], child["wiki_page_id"]} <= trashed


async def test_restore_page_returns_it_to_tree(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    assert (await wiki_client.delete(f"{PAGES_URL}/{page_id}")).status_code == 204

    response = await wiki_client.post(f"{PAGES_URL}/{page_id}/restore")

    assert response.status_code == 200, response.text
    tree = await wiki_client.get(PAGES_URL)
    assert page_id in {item["wiki_page_id"] for item in tree.json()["items"]}


async def test_children_endpoint_returns_direct_descendants(wiki_client, create_page, unique_id):
    parent = await create_page(f"Каталог {unique_id}")
    child = await create_page(f"Первый {unique_id}", parent_page_id=parent["wiki_page_id"])
    grandchild = await create_page(f"Внук {unique_id}", parent_page_id=child["wiki_page_id"])

    response = await wiki_client.get(f"{PAGES_URL}/{parent['wiki_page_id']}/children")

    assert response.status_code == 200, response.text
    returned = {item["wiki_page_id"] for item in response.json()["items"]}
    assert returned == {child["wiki_page_id"]}
    assert grandchild["wiki_page_id"] not in returned


async def test_request_without_namespace_header_falls_into_default_space(
    wiki_app, auth_headers_system, wiki_page
):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=wiki_app),
        base_url="http://testserver",
        headers=auth_headers_system,
    ) as client:
        response = await client.get(PAGES_URL)

    # Без заголовка платформа адресует запрос системному `default`. Это
    # существующее пространство, а не отсутствие границы: страницы тестового
    # пространства в него не протекают.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["namespace"] == "default"
    assert wiki_page["wiki_page_id"] not in {item["wiki_page_id"] for item in body["items"]}


async def test_unknown_namespace_is_rejected(wiki_app, wiki_di, auth_headers_system):
    from httpx import ASGITransport, AsyncClient

    _ = wiki_di

    async with AsyncClient(
        transport=ASGITransport(app=wiki_app),
        base_url="http://testserver",
        headers={**auth_headers_system, "X-Platform-Namespace": "no-such-space"},
    ) as client:
        response = await client.get(PAGES_URL)

    assert response.status_code == 400


async def test_require_scope_without_namespace_view_returns_403(
    wiki_client, wiki_di, wiki_namespace: str
) -> None:
    obj = AuthzObject.platform_namespace("system", wiki_namespace)
    tuples = await wiki_di.authz_service.list_tuples(obj)
    if tuples:
        await wiki_di.authz_service.delete(tuples)
    response = await wiki_client.get(PAGES_URL)
    assert response.status_code == 403


async def test_health_endpoint_is_public(wiki_client_anonymous):
    response = await wiki_client_anonymous.get("/health")

    assert response.status_code == 200


async def test_api_requires_authentication(wiki_client_anonymous):
    response = await wiki_client_anonymous.get(PAGES_URL)

    assert response.status_code in (401, 403)


async def test_search_endpoint_is_registered(wiki_client):
    response = await wiki_client.post(
        f"{API_PREFIX}/search", json={"query": "проверка", "mode": "lexical"}
    )

    assert response.status_code == 200, response.text
    assert isinstance(response.json()["items"], list)
