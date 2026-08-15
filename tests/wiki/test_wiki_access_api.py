"""
Доступ к страницам: участники, company_visible, публичные ссылки.

Проверяется настоящий путь: два реальных пользователя одной компании,
пользователь чужой компании и анонимный клиент. Единственный PDP — OpenFGA
(`wiki_page`): `company_visible` — прямой (не каскадирующий) тег страницы,
даёт компании только `can_view` (не `can_edit`); `viewer`/`editor` —
участники страницы, унаследуемые её поддеревом через TTU `parent`.
Владелец получает `can_admin`/`can_edit`/`can_view` через FGA `owner`
сразу при создании — добавлять его отдельным участником не нужно.
"""

from __future__ import annotations

import pytest

from core.utils.tokens import get_token_service
from tests.wiki.conftest import PAGES_URL

pytestmark = pytest.mark.no_test_doubles


def _user_id_from_token(auth_token: str) -> str:
    token_data = get_token_service().validate_token(auth_token)
    if token_data is None:
        raise ValueError("invalid auth token in test fixture")
    return token_data.user_id


async def test_page_without_restrictions_is_readable_by_colleague(
    wiki_page, wiki_client_member
):
    response = await wiki_client_member.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}")

    assert response.status_code == 200, response.text
    assert response.json()["page"]["wiki_page_id"] == wiki_page["wiki_page_id"]


async def test_page_without_restrictions_is_view_only_for_colleague(
    wiki_page, wiki_client_member
):
    """company_visible=true → company#member company_viewer: can_view, не can_edit."""
    response = await wiki_client_member.put(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/content",
        json={"markdown": "Правка коллеги"},
    )

    assert response.status_code == 403, response.text


async def test_access_defaults_to_company_visible(wiki_client, wiki_page):
    response = await wiki_client.get(f"{PAGES_URL}/{wiki_page['wiki_page_id']}/access")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["company_visible"] is True
    assert body["members"] == []
    assert body["inherited_from_page_id"] is None
    assert body["link_enabled"] is False


async def test_restricting_page_denies_access_to_colleague_but_not_owner(
    wiki_client, wiki_client_member, wiki_page, stored_page
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible",
        json={"company_visible": False},
    )

    assert response.status_code == 200, response.text
    assert response.json()["company_visible"] is False

    saved = await stored_page(page_id)
    assert saved.company_visible is False

    denied = await wiki_client_member.get(f"{PAGES_URL}/{page_id}")
    assert denied.status_code == 403

    owner_still_ok = await wiki_client.get(f"{PAGES_URL}/{page_id}")
    assert owner_still_ok.status_code == 200


async def test_adding_member_requires_company_visible_false(wiki_client, wiki_page, system_user_id):
    response = await wiki_client.post(
        f"{PAGES_URL}/{wiki_page['wiki_page_id']}/access/members",
        json={"user_id": system_user_id, "relation": "viewer"},
    )

    assert response.status_code == 400, response.text


async def test_new_child_inherits_restricted_company_visible_from_parent(
    wiki_client, wiki_client_member, create_page, unique_id, stored_page
):
    parent = await create_page(f"Закрытый раздел {unique_id}")
    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restrict.status_code == 200, restrict.text

    child = await create_page(f"Вложенная {unique_id}", parent_page_id=parent["wiki_page_id"])

    child_state = await stored_page(child["wiki_page_id"])
    assert child_state.company_visible is False

    denied = await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    assert denied.status_code == 403

    access = await wiki_client.get(f"{PAGES_URL}/{child['wiki_page_id']}/access")
    assert access.json()["company_visible"] is False
    # Ребёнок восстанавливает своё собственное прямое ограничение, а не наследует чужое.
    assert access.json()["inherited_from_page_id"] is None


async def test_inherited_from_page_id_points_to_ancestor_restricted_after_creation(
    wiki_client, create_page, unique_id
):
    """`inherited_from_page_id` — ближайший предок с company_visible=false для UI дерева.

    `company` tuple не каскадирует в FGA: страница, созданная публичной до того, как
    предка ограничили, остаётся видимой сама по себе, но UI должен показать, из-за
    какого предка ветка выглядит закрытой.
    """
    parent = await create_page(f"Родитель {unique_id}")
    child = await create_page(f"Ребёнок {unique_id}", parent_page_id=parent["wiki_page_id"])

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restrict.status_code == 200, restrict.text

    access = await wiki_client.get(f"{PAGES_URL}/{child['wiki_page_id']}/access")
    assert access.json()["company_visible"] is True
    assert access.json()["inherited_from_page_id"] == parent["wiki_page_id"]


async def test_member_added_on_parent_grants_child_access_via_ttu(
    wiki_client, wiki_client_member, create_page, unique_id, auth_token_system_user2
):
    """`viewer`/`editor` каскадируют поддереву через TTU `parent`, в отличие от `company_visible`."""
    member_id = _user_id_from_token(auth_token_system_user2)
    parent = await create_page(f"Закрытый раздел {unique_id}")
    child = await create_page(f"Вложенная {unique_id}", parent_page_id=parent["wiki_page_id"])

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restrict.status_code == 200, restrict.text

    granted = await wiki_client.post(
        f"{PAGES_URL}/{parent['wiki_page_id']}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert granted.status_code == 200, granted.text

    child_response = await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    assert child_response.status_code == 200, child_response.text


async def test_restriction_does_not_leak_to_sibling(
    wiki_client, wiki_client_member, create_page, unique_id
):
    root = await create_page(f"Общий {unique_id}")
    closed = await create_page(f"Закрытая {unique_id}", parent_page_id=root["wiki_page_id"])
    sibling = await create_page(f"Открытая {unique_id}", parent_page_id=root["wiki_page_id"])

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{closed['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restrict.status_code == 200, restrict.text

    assert (await wiki_client_member.get(f"{PAGES_URL}/{closed['wiki_page_id']}")).status_code == 403
    assert (await wiki_client_member.get(f"{PAGES_URL}/{sibling['wiki_page_id']}")).status_code == 200


async def test_member_with_viewer_relation_cannot_edit(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2
):
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    assert restrict.status_code == 200, restrict.text

    granted = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert granted.status_code == 200, granted.text

    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    edit = await wiki_client_member.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Попытка правки"}
    )
    assert edit.status_code == 403


async def test_member_with_editor_relation_can_edit(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2
):
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    granted = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "editor"},
    )
    assert granted.status_code == 200, granted.text

    edit = await wiki_client_member.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Правка разрешена"}
    )
    assert edit.status_code == 200, edit.text


async def test_setting_company_visible_true_restores_colleague_access_and_clears_members(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2, stored_page
):
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    restored = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": True}
    )

    assert restored.status_code == 200, restored.text
    assert restored.json()["company_visible"] is True
    assert restored.json()["members"] == []
    assert (await stored_page(page_id)).company_visible is True
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200


async def test_restricted_page_disappears_from_colleague_tree(
    wiki_client, wiki_client_member, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    visible_before = await wiki_client_member.get(PAGES_URL)
    assert page_id in {item["wiki_page_id"] for item in visible_before.json()["items"]}

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    assert restrict.status_code == 200, restrict.text

    visible_after = await wiki_client_member.get(PAGES_URL)
    assert page_id not in {item["wiki_page_id"] for item in visible_after.json()["items"]}


async def test_public_link_url_uses_request_origin_not_internal_service(
    wiki_client, wiki_page
):
    """Публичный URL строится из Host запроса, не из SERVER__FRONTEND_SERVICE_URL."""
    page_id = wiki_page["wiki_page_id"]
    public_host = "jfj-designs.linnex.io"

    response = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/link",
        json={"enabled": True, "permission": "viewer"},
        headers={
            "Host": public_host,
            "X-Forwarded-Host": public_host,
            "X-Forwarded-Proto": "https",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["enabled"] is True
    assert isinstance(body["url"], str)
    assert body["url"].startswith(f"https://{public_host}/wiki/s/")
    assert "frontend" not in body["url"]
    assert ":8002" not in body["url"]


async def test_public_link_opens_page_for_anonymous(
    wiki_client, wiki_client_anonymous, wiki_page
):
    page_id = wiki_page["wiki_page_id"]

    response = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True, "permission": "viewer"}
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


async def test_draft_page_is_not_available_by_public_link(
    wiki_client, wiki_client_anonymous, wiki_page
):
    """Черновик по ссылке не отдаётся, даже если ссылка включена."""
    page_id = wiki_page["wiki_page_id"]
    link = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    token = link.json()["url"].rsplit("/", 1)[-1]

    unpublished = await wiki_client.patch(f"{PAGES_URL}/{page_id}", json={"is_published": False})

    assert unpublished.status_code == 200, unpublished.text
    assert (await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")).status_code == 404
    assert (
        await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}/markdown")
    ).status_code == 404


async def test_publishing_page_again_restores_public_link(
    wiki_client, wiki_client_anonymous, wiki_page
):
    """Токен переживает снятие публикации: возвращать его повторно не нужно."""
    page_id = wiki_page["wiki_page_id"]
    link = await wiki_client.post(f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True})
    token = link.json()["url"].rsplit("/", 1)[-1]
    assert (
        await wiki_client.patch(f"{PAGES_URL}/{page_id}", json={"is_published": False})
    ).status_code == 200

    published = await wiki_client.patch(f"{PAGES_URL}/{page_id}", json={"is_published": True})

    assert published.status_code == 200, published.text
    assert (await wiki_client_anonymous.get(f"/wiki/api/v1/public/pages/{token}")).status_code == 200


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


async def test_editor_member_can_edit_but_cannot_share_or_admin(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2, system_user_id
):
    """`editor` даёт can_edit, но can_share/can_admin — только у owner."""
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    assert restrict.status_code == 200, restrict.text
    granted = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "editor"},
    )
    assert granted.status_code == 200, granted.text

    edit = await wiki_client_member.put(
        f"{PAGES_URL}/{page_id}/content", json={"markdown": "Правка editor"}
    )
    assert edit.status_code == 200, edit.text

    # GET access разрешён любому с can_view (в отличие от Office catalog GET).
    access = await wiki_client_member.get(f"{PAGES_URL}/{page_id}/access")
    assert access.status_code == 200, access.text

    assert (
        await wiki_client_member.patch(
            f"{PAGES_URL}/{page_id}/access/company-visible",
            json={"company_visible": True},
        )
    ).status_code == 403
    assert (
        await wiki_client_member.post(
            f"{PAGES_URL}/{page_id}/access/members",
            json={"user_id": system_user_id, "relation": "viewer"},
        )
    ).status_code == 403
    assert (
        await wiki_client_member.delete(f"{PAGES_URL}/{page_id}/access/members/{member_id}")
    ).status_code == 403
    assert (
        await wiki_client_member.post(
            f"{PAGES_URL}/{page_id}/access/link", json={"enabled": True}
        )
    ).status_code == 403
    assert (await wiki_client_member.delete(f"{PAGES_URL}/{page_id}")).status_code == 403


async def test_owner_is_not_listed_among_explicit_members(
    wiki_client, wiki_page, auth_token_system_user2, system_user_id
):
    """list_member_items читает только прямые viewer/editor — owner не дублируется."""
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    granted = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert granted.status_code == 200, granted.text

    members = granted.json()["members"]
    member_ids = {row["user_id"] for row in members}
    assert member_id in member_ids
    assert system_user_id not in member_ids
    assert all(row["relation"] in {"viewer", "editor"} for row in members)


async def test_removing_member_revokes_peer_access(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2
):
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    removed = await wiki_client.delete(f"{PAGES_URL}/{page_id}/access/members/{member_id}")
    assert removed.status_code == 200, removed.text
    assert all(row["user_id"] != member_id for row in removed.json()["members"])
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 403


async def test_private_child_under_public_parent_is_company_island(
    wiki_client, wiki_client_member, create_page, unique_id
):
    """company_viewer не каскадирует через parent: закрытый ребёнок — остров."""
    parent = await create_page(f"Открытый раздел {unique_id}")
    child = await create_page(f"Закрытый остров {unique_id}", parent_page_id=parent["wiki_page_id"])

    restrict = await wiki_client.patch(
        f"{PAGES_URL}/{child['wiki_page_id']}/access/company-visible",
        json={"company_visible": False},
    )
    assert restrict.status_code == 200, restrict.text

    assert (
        await wiki_client_member.get(f"{PAGES_URL}/{parent['wiki_page_id']}")
    ).status_code == 200
    assert (
        await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    ).status_code == 403

    tree = await wiki_client_member.get(PAGES_URL)
    ids = {item["wiki_page_id"] for item in tree.json()["items"]}
    assert parent["wiki_page_id"] in ids
    assert child["wiki_page_id"] not in ids


async def test_move_rewrites_parent_ttu_and_revokes_old_parent_membership(
    wiki_client, wiki_client_member, create_page, unique_id, auth_token_system_user2
):
    """После move TTU `parent` переписывается: членство на старом родителе не тянется."""
    member_id = _user_id_from_token(auth_token_system_user2)
    source_parent = await create_page(f"Источник {unique_id}")
    target_parent = await create_page(f"Цель {unique_id}")
    child = await create_page(
        f"Переезд {unique_id}", parent_page_id=source_parent["wiki_page_id"]
    )

    for page_id in (
        source_parent["wiki_page_id"],
        target_parent["wiki_page_id"],
        child["wiki_page_id"],
    ):
        restrict = await wiki_client.patch(
            f"{PAGES_URL}/{page_id}/access/company-visible",
            json={"company_visible": False},
        )
        assert restrict.status_code == 200, restrict.text

    granted = await wiki_client.post(
        f"{PAGES_URL}/{source_parent['wiki_page_id']}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert granted.status_code == 200, granted.text
    assert (
        await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    ).status_code == 200

    moved = await wiki_client.post(
        f"{PAGES_URL}/{child['wiki_page_id']}/move",
        json={"parent_page_id": target_parent["wiki_page_id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["page"]["parent_page_id"] == target_parent["wiki_page_id"]

    assert (
        await wiki_client_member.get(f"{PAGES_URL}/{child['wiki_page_id']}")
    ).status_code == 403
    assert (
        await wiki_client_member.get(f"{PAGES_URL}/{source_parent['wiki_page_id']}")
    ).status_code == 200


async def test_delete_clears_fga_and_restore_rebuilds_owner_without_members(
    wiki_client, wiki_client_member, wiki_page, auth_token_system_user2
):
    """soft-delete зачищает tuples; restore поднимает owner/parent/company, не members."""
    member_id = _user_id_from_token(auth_token_system_user2)
    page_id = wiki_page["wiki_page_id"]

    _ = await wiki_client.patch(
        f"{PAGES_URL}/{page_id}/access/company-visible", json={"company_visible": False}
    )
    _ = await wiki_client.post(
        f"{PAGES_URL}/{page_id}/access/members",
        json={"user_id": member_id, "relation": "viewer"},
    )
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    assert (await wiki_client.delete(f"{PAGES_URL}/{page_id}")).status_code == 204
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 404

    restored = await wiki_client.post(f"{PAGES_URL}/{page_id}/restore")
    assert restored.status_code == 200, restored.text

    owner_get = await wiki_client.get(f"{PAGES_URL}/{page_id}")
    assert owner_get.status_code == 200, owner_get.text
    assert owner_get.json()["can_admin"] is True

    access = await wiki_client.get(f"{PAGES_URL}/{page_id}/access")
    assert access.status_code == 200, access.text
    assert access.json()["company_visible"] is False
    assert access.json()["members"] == []

    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 403


async def test_restore_company_visible_page_returns_colleague_access(
    wiki_client, wiki_client_member, wiki_page
):
    page_id = wiki_page["wiki_page_id"]
    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200

    assert (await wiki_client.delete(f"{PAGES_URL}/{page_id}")).status_code == 204
    assert (await wiki_client.post(f"{PAGES_URL}/{page_id}/restore")).status_code == 200

    assert (await wiki_client_member.get(f"{PAGES_URL}/{page_id}")).status_code == 200
