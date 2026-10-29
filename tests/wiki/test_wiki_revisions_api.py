"""
История версий: снимок при каждой записи и обратимый откат.
"""

from __future__ import annotations

import pytest
from httpx2 import Response

from core.types import JsonObject, require_json_object
from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


def _revision_items(response: Response) -> list[JsonObject]:
    body = require_json_object(response.json(), "revisions")
    items = body.get("items")
    if not isinstance(items, list):
        raise AssertionError("revisions payload.items must be a list")
    return [require_json_object(item, "revision") for item in items]


async def test_first_save_creates_single_revision(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]

    saved = await wiki_client.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Вторая версия."}
    )
    assert saved.status_code == 200, saved.text

    revisions = await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions")
    assert revisions.status_code == 200, revisions.text
    items = _revision_items(revisions)
    assert len(items) == 1
    assert items[0]["wiki_page_id"] == page_id


async def test_revisions_are_returned_newest_first(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    for text in ("Версия 2.", "Версия 3.", "Версия 4."):
        response = await wiki_client.put(
            f"{PAGES_URL}/{page_id}/content", json={"markdown": text}
        )
        assert response.status_code == 200, response.text

    items = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))

    assert len(items) == 3
    timestamps = [item["created_at"] for item in items]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_revision_keeps_previous_content(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.put(f"{PAGES_URL}/{page_id}/content", json={"markdown": "Заменено."})

    revision_id = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))[0][
        "wiki_revision_id"
    ]
    revision = await wiki_client.get(f"{API_PREFIX}/revisions/{revision_id}")

    assert revision.status_code == 200, revision.text
    # В ревизии лежит состояние ДО правки — иначе откатываться было бы некуда.
    assert revision.json()["text_markdown"].startswith("# Заголовок")


async def test_save_without_revision_does_not_grow_history(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.put(
        f"{PAGES_URL}/{page_id}/content",
        json={"markdown": "Автосохранение.", "create_revision": False},
    )

    assert response.status_code == 200, response.text
    assert _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions")) == []


async def test_restore_revision_returns_previous_text(wiki_client, wiki_page, stored_page):
    page_id = wiki_page["wiki_page_id"]
    original = (await stored_page(page_id)).text_markdown
    _ = await wiki_client.put(f"{PAGES_URL}/{page_id}/content", json={"markdown": "Ошибка."})

    revision_id = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))[0][
        "wiki_revision_id"
    ]
    restored = await wiki_client.post(f"{API_PREFIX}/revisions/{revision_id}/restore")

    assert restored.status_code == 200, restored.text
    assert (await stored_page(page_id)).text_markdown == original


async def test_restore_is_itself_reversible(wiki_client, wiki_page, stored_page):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.put(f"{PAGES_URL}/{page_id}/content", json={"markdown": "Версия Б."})

    first_revision = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))[0]
    _ = await wiki_client.post(
        f"{API_PREFIX}/revisions/{first_revision['wiki_revision_id']}/restore"
    )

    # Откат сам записал версию Б в историю, поэтому вернуться к ней можно.
    history = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))
    assert len(history) == 2
    back = await wiki_client.post(
        f"{API_PREFIX}/revisions/{history[0]['wiki_revision_id']}/restore"
    )
    assert back.status_code == 200, back.text
    assert (await stored_page(page_id)).text_markdown == "Версия Б."


async def test_revision_of_foreign_namespace_is_not_readable(
    wiki_client, wiki_client_other_namespace, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.put(f"{PAGES_URL}/{page_id}/content", json={"markdown": "Правка."})
    revision_id = _revision_items(await wiki_client.get(f"{PAGES_URL}/{page_id}/revisions"))[0][
        "wiki_revision_id"
    ]

    response = await wiki_client_other_namespace.get(f"{API_PREFIX}/revisions/{revision_id}")

    assert response.status_code == 404


async def test_revisions_of_restricted_page_are_closed_for_colleague(
    wiki_client, wiki_client_member, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.put(f"{PAGES_URL}/{page_id}/content", json={"markdown": "Правка."})
    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )

    response = await wiki_client_member.get(f"{PAGES_URL}/{page_id}/revisions")

    assert response.status_code == 403


async def test_unknown_revision_returns_404(wiki_client):
    response = await wiki_client.get(f"{API_PREFIX}/revisions/wrv_missing")

    assert response.status_code == 404
