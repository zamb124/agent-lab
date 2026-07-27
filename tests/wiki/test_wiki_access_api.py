"""
Доступ к страницам: участники, наследование ограничений, публичные ссылки.

Проверяется настоящий путь: два реальных пользователя одной компании,
пользователь чужой компании и анонимный клиент. Ограничение ставится на
страницу и должно наследоваться поддеревом, а видимость — переключать слой
индексации.
"""

from __future__ import annotations

import pytest

from apps.wiki.models.domain import WikiVisibility
from tests.wiki.conftest import PAGES_URL

pytestmark = pytest.mark.no_test_doubles


async def test_page_without_restrictions_is_readable_by_colleague(
    wiki_page, wiki_client_member
):
    response = await wiki_client_member.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}")

    assert response.status_code == 200, response.text
    assert response.json()["page"]["wiki_page_id"] == wiki_page["wiki_page_id"]


async def test_page_without_restrictions_is_editable_by_colleague(
    wiki_page, wiki_client_member
):
    response = await wiki_client_member.put(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/content",
        json={"markdown": "Правка коллеги"},
    )

    assert response.status_code == 200, response.text


async def test_access_defaults_to_company_visibility(wiki_client, wiki_page):
    response = await wiki_client.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}/access")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visibility"] == WikiVisibility.COMPANY.value
    assert body["members"] == []
    assert body["inherited_from_page_id"] is None
    assert body["link_enabled"] is False


async def test_adding_member_restricts_page_for_others(
    wiki_client, wiki_client_member, wiki_page, system_user_id, stored_page
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["visibility"] == WikiVisibility.RESTRICTED.value

    saved = await stored_page(page_id)
    assert saved.visibility == WikiVisibility.RESTRICTED

    denied = await wiki_client_member.get(f"{PAGES_URL}/{page_id}")
    assert denied.status_code == 403


async def test_restriction_is_inherited_by_child_page(
    wiki_client, wiki_client_member, create_page, system_user_id, unique_id, stored_page
):
    parent = await create_page(f"Закрытый раздел {unique_id}")
    child = await create_page(f"Вложенная {unique_id}", parent_page_id=parent["wiki_page_id"])

    grant = await wiki_client.post(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )
    assert grant.status_code == 200, grant.text

    child_state = await stored_page(child["wiki_page_id"])
    assert child_state.visibility == WikiVisibility.RESTRICTED

    denied = await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    assert denied.status_code == 403

    access = await wiki_client.get(f"{PAGES_URL}/{child['wiki_page_id']}/access")
    assert access.json()["inherited_from_page_id"] == parent["wiki_page_id"]


async def test_restriction_does_not_leak_to_sibling(
    wiki_client, wiki_client_member, create_page, system_user_id, unique_id
):
    root = await create_page(f"Общий {unique_id}")
    closed = await create_page(f"Закрытая {unique_id}", parent_page_id=root["wiki_page_id"])
    sibling = await create_page(f"Открытая {unique_id}", parent_page_id=root["wiki_page_id"])

    grant = await wiki_client.post(
        f"{PAGES_URL}/{closed['wiki_page_id']}/access/members",
        json={"user_id": system_user_id, "permission": "read"},
    )
    assert grant.status_code == 200, grant.text

    assert (await wiki_client_member.get(f"{PAGES_URL}/{closed['wiki_page_id']}")).status_code == 403
    assert (await wiki_client_member.get(f"{PAGES_URL}/{sibling['wiki_page_id']}")).status_code == 200


async def test_member_with_read_permission_cannot_edit(
    wiki_client, wiki_client_member, wiki_page, system_user_id, auth_token_system_user2
):
    from core.utils.tokens import get_token_service

    member_id = get_token_service().validate_token(auth_token_system_user2).user_id
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )
    granted = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "permission": "read"},
    )
    assert granted.status_code == 200, granted.text

    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    edit = await wiki_client_member.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Попытка правки"}
    )
    assert edit.status_code == 403


async def test_member_with_write_permission_can_edit(
    wiki_client, wiki_client_member, wiki_page, system_user_id, auth_token_system_user2
):
    from core.utils.tokens import get_token_service

    member_id = get_token_service().validate_token(auth_token_system_user2).user_id
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )
    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "permission": "write"},
    )

    edit = await wiki_client_member.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Правка разрешена"}
    )
    assert edit.status_code == 200, edit.text


async def test_removing_last_member_returns_page_to_company(
    wiki_client, wiki_client_member, wiki_page, system_user_id, stored_page
):
    page_id = wiki_page["wiki_page_id"]
    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 403

    removed = await wiki_client.delete(
        f"{PAGES_URL}/{page_id}/access/members/{system_user_id}"
    )

    assert removed.status_code == 200, removed.text
    assert removed.json()["visibility"] == WikiVisibility.COMPANY.value
    assert (await stored_page(page_id)).visibility == WikiVisibility.COMPANY
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200


async def test_restricted_page_disappears_from_colleague_tree(
    wiki_client, wiki_client_member, wiki_page, system_user_id
):
    page_id = wiki_page["wiki_page_id"]
    visible_before = await wiki_client_member.get(PAGES_URL)
    assert page_id in {item["wiki_page_id"] for item in visible_before.json()["items"]}

    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": system_user_id, "permission": "admin"},
    )

    visible_after = await wiki_client_member.get(PAGES_URL)
    assert page_id not in {item["wiki_page_id"] for item in visible_after.json()["items"]}


async def test_public_link_opens_page_for_anonymous(
    wiki_client, wiki_client_anonymous, wiki_page
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True, "permission": "view"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    token = body["url"].rsplit("/", 1)[-1]

    public = await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")
    assert public.status_code == 200, public.text
    assert public.json()["wiki_page_id"] == page_id
    assert public.json()["content"]["type"] == "doc"


async def test_public_link_markdown_is_available_for_anonymous(
    wiki_client, wiki_client_anonymous, wiki_page
):
    link = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/access/link", json={"enabled": True}
    )
    token = link.json()["url"].rsplit("/", 1)[-1]

    public = await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}/markdown")

    assert public.status_code == 200, public.text
    assert public.json()["markdown"].startswith("# Заголовок")


async def test_disabling_public_link_revokes_anonymous_access(
    wiki_client, wiki_client_anonymous, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    link = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    token = link.json()["url"].rsplit("/", 1)[-1]
    assert (await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")).status_code == 200

    disabled = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/link", json={"enabled": False}
    )

    assert disabled.status_code == 200, disabled.text
    assert disabled.json()["url"] is None
    assert (await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")).status_code == 404


async def test_rotating_public_link_invalidates_previous_token(
    wiki_client, wiki_client_anonymous, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    first = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    first_token = first.json()["url"].rsplit("/", 1)[-1]

    second = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    second_token = second.json()["url"].rsplit("/", 1)[-1]

    assert first_token != second_token
    assert (
        await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{first_token}")
    ).status_code == 404
    assert (
        await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{second_token}")
    ).status_code == 200


async def test_unknown_public_token_returns_404(wiki_client_anonymous):
    response = await wiki_client_anonymous.get("/wiki/api/v1/public/pages/not-a-real-token")

    assert response.status_code == 404


async def test_deleted_page_is_not_available_by_public_link(
    wiki_client, wiki_client_anonymous, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    link = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    token = link.json()["url"].rsplit("/", 1)[-1]

    assert (await wiki_client.delete(f"{PAGES_URL}/{page_id}")).status_code == 204

    assert (await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")).status_code == 404
