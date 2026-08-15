"""
Доменные события wiki на шине `platform:events`.

События читаются из реального Redis Stream: проверяется, что факт изменения
страницы доходит до потребителей и что в него не утекает содержимое —
рассылка идёт всей компании, а текст может быть ограниченным.
"""

from __future__ import annotations

import pytest

from apps.wiki.events import (
    WIKI_COMMENT_CREATED,
    WIKI_PAGE_ACCESS_CHANGED,
    WIKI_PAGE_CREATED,
    WIKI_PAGE_DELETED,
    WIKI_PAGE_MOVED,
    WIKI_PAGE_UPDATED,
)
from tests.wiki.conftest import PAGES_URL

pytestmark = pytest.mark.no_test_doubles

EVENT_TIMEOUT = 2.0


async def test_page_creation_publishes_event(
    wiki_client, platform_events_listener, unique_id
):
    response = await wiki_client.post(
        PAGES_URL, json={"title": f"Событие {unique_id}", "markdown": "Текст."}
    )
    assert response.status_code == 201, response.text
    page_id = response.json()["page"]["wiki_page_id"]

    events = await platform_events_listener(WIKI_PAGE_CREATED, None, EVENT_TIMEOUT)

    published = [
        event for event in events if event["payload"]["page"]["wiki_page_id"] == page_id
    ]
    assert len(published) == 1
    assert published[0]["company_id"] == "system"


async def test_page_event_does_not_carry_content(
    wiki_client, platform_events_listener, unique_id
):
    secret = f"секретнаястрока{unique_id}"
    response = await wiki_client.post(
        PAGES_URL, json={"title": f"Тайна {unique_id}", "markdown": f"Текст {secret}."}
    )
    page_id = response.json()["page"]["wiki_page_id"]

    events = await platform_events_listener(WIKI_PAGE_CREATED, None, EVENT_TIMEOUT)

    payload = next(
        event["payload"] for event in events if event["payload"]["page"]["wiki_page_id"] == page_id
    )
    assert "content" not in payload["page"]
    assert secret not in str(payload)


async def test_content_update_publishes_event(wiki_client, wiki_page, platform_events_listener):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Изменено."}
    )
    assert response.status_code == 200, response.text

    events = await platform_events_listener(WIKI_PAGE_UPDATED, None, EVENT_TIMEOUT)

    assert any(event["payload"]["page"]["wiki_page_id"] == page_id for event in events)


async def test_move_publishes_event_with_previous_location(
    wiki_client, create_page, platform_events_listener, unique_id
):
    parent = await create_page(f"Новый родитель {unique_id}")
    page = await create_page(f"Переносимая {unique_id}")

    response = await wiki_client.post(
        f"{PAGES_URL}/{page['wiki_page_id']}/move",
        json={"parent_page_id": parent["wiki_page_id"]},
    )
    assert response.status_code == 200, response.text

    events = await platform_events_listener(WIKI_PAGE_MOVED, None, EVENT_TIMEOUT)

    payload = next(
        event["payload"]
        for event in events
        if event["payload"]["page"]["wiki_page_id"] == page["wiki_page_id"]
    )
    assert payload["page"]["parent_page_id"] == parent["wiki_page_id"]
    assert payload["previous_parent_page_id"] is None


async def test_delete_publishes_event_with_affected_subtree(
    wiki_client, create_page, platform_events_listener, unique_id
):
    parent = await create_page(f"Корень {unique_id}")
    child = await create_page(f"Ветка {unique_id}", parent_page_id=parent["wiki_page_id"])

    assert (await wiki_client.delete(f"{PAGES_URL}/{parent['wiki_page_id']}")).status_code == 204

    events = await platform_events_listener(WIKI_PAGE_DELETED, None, EVENT_TIMEOUT)

    payload = next(
        event["payload"]
        for event in events
        if event["payload"]["wiki_page_id"] == parent["wiki_page_id"]
    )
    assert set(payload["affected_page_ids"]) == {parent["wiki_page_id"], child["wiki_page_id"]}


async def test_access_change_publishes_visibility_event(
    wiki_client, wiki_page, platform_events_listener
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )
    assert response.status_code == 200, response.text

    events = await platform_events_listener(WIKI_PAGE_ACCESS_CHANGED, None, EVENT_TIMEOUT)

    payload = next(
        event["payload"] for event in events if event["payload"]["wiki_page_id"] == page_id
    )
    assert payload["visibility"] == "restricted"
    assert page_id in payload["affected_page_ids"]


async def test_comment_publishes_event(wiki_client, wiki_page, platform_events_listener):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": "Комментарий"}
    )
    assert response.status_code == 201, response.text

    events = await platform_events_listener(WIKI_COMMENT_CREATED, None, EVENT_TIMEOUT)

    assert any(event["payload"]["comment"]["wiki_page_id"] == page_id for event in events)


async def test_wiki_event_types_are_registered_in_catalog():
    from core.events.registry import registered_platform_event_types

    registered = set(registered_platform_event_types())

    assert {
        WIKI_PAGE_CREATED,
        WIKI_PAGE_UPDATED,
        WIKI_PAGE_MOVED,
        WIKI_PAGE_DELETED,
        WIKI_PAGE_ACCESS_CHANGED,
        WIKI_COMMENT_CREATED,
    } <= registered
