"""
Комментарии к странице: обсуждение, ветки, закрытие.
"""

from __future__ import annotations

import pytest

from tests.wiki.conftest import API_PREFIX, PAGES_URL

pytestmark = pytest.mark.no_test_doubles


async def test_new_page_has_no_comments(wiki_client, wiki_page):
    response = await wiki_client.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments")

    assert response.status_code == 200, response.text
    assert response.json()["items"] == []


async def test_create_comment_returns_author_and_body(wiki_client, wiki_page, system_user_id):
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments",
        json={"body_markdown": "Нужно уточнить срок", "anchor_text": "срок"},
    )

    assert response.status_code == 201, response.text
    comment = response.json()
    assert comment["body_markdown"] == "Нужно уточнить срок"
    assert comment["anchor_text"] == "срок"
    assert comment["author_user_id"] == system_user_id
    assert comment["resolved_at"] is None


async def test_comments_are_listed_in_chronological_order(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    for text in ("Первый", "Второй", "Третий"):
        response = await wiki_client.post(
            f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": text}
        )
        assert response.status_code == 201, response.text

    items = (await wiki_client.get(f"{PAGES_URL}/{page_id}/comments")).json()["items"]

    assert [item["body_markdown"] for item in items] == ["Первый", "Второй", "Третий"]


async def test_reply_keeps_parent_reference(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    root = (
        await wiki_client.post(
            f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": "Вопрос"}
        )
    ).json()

    reply = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/comments",
        json={"body_markdown": "Ответ", "parent_comment_id": root["wiki_comment_id"]},
    )

    assert reply.status_code == 201, reply.text
    assert reply.json()["parent_comment_id"] == root["wiki_comment_id"]


async def test_resolve_marks_comment_closed(wiki_client, wiki_page, system_user_id):
    comment = (
        await wiki_client.post(
            f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments",
            json={"body_markdown": "Поправить"},
        )
    ).json()

    response = await wiki_client.post(
        f"{API_PREFIX}/comments/{comment['wiki_comment_id']}/resolve", json={"resolved": True}
    )

    assert response.status_code == 200, response.text
    assert response.json()["resolved_at"] is not None
    assert response.json()["resolved_by_user_id"] == system_user_id


async def test_unresolve_reopens_comment(wiki_client, wiki_page):
    comment = (
        await wiki_client.post(
            f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments",
            json={"body_markdown": "Обсудить"},
        )
    ).json()
    comment_id = comment["wiki_comment_id"]
    _ = await wiki_client.post(f"{API_PREFIX}/comments/{comment_id}/resolve", json={"resolved": True})

    response = await wiki_client.post(
        f"{API_PREFIX}/comments/{comment_id}/resolve", json={"resolved": False}
    )

    assert response.status_code == 200, response.text
    assert response.json()["resolved_at"] is None
    assert response.json()["resolved_by_user_id"] is None


async def test_delete_comment_removes_it_from_thread(wiki_client, wiki_page):
    page_id = wiki_page["wiki_page_id"]
    comment = (
        await wiki_client.post(
            f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": "Лишний"}
        )
    ).json()

    deleted = await wiki_client.delete(f"{API_PREFIX}/comments/{comment['wiki_comment_id']}")

    assert deleted.status_code == 204
    assert (await wiki_client.get(f"{PAGES_URL}/{page_id}/comments")).json()["items"] == []


async def test_colleague_can_comment_open_page(wiki_client_member, wiki_page):
    response = await wiki_client_member.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments",
        json={"body_markdown": "Комментарий коллеги"},
    )

    assert response.status_code == 201, response.text


async def test_comments_of_restricted_page_are_closed_for_colleague(
    wiki_client, wiki_client_member, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )

    listing = await wiki_client_member.get(f"{PAGES_URL}/{page_id}/comments")
    creating = await wiki_client_member.post(
        f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": "Попытка"}
    )

    assert listing.status_code == 403
    assert creating.status_code == 403


async def test_comments_do_not_leak_between_namespaces(
    wiki_client, wiki_client_other_namespace, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.post(f"{PAGES_URL}/{page_id}/comments", json={"body_markdown": "Свой"})

    response = await wiki_client_other_namespace.get(f"{PAGES_URL}/{page_id}/comments")

    assert response.status_code == 404


async def test_comment_on_missing_page_returns_404(wiki_client):
    response = await wiki_client.post(
        f"{PAGES_URL}/wpg_missing/comments", json={"body_markdown": "Текст"}
    )

    assert response.status_code == 404


async def test_empty_comment_body_is_rejected(wiki_client, wiki_page):
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/comments", json={"body_markdown": ""}
    )

    assert response.status_code == 422
