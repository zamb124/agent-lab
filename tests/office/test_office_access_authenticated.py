"""Authenticated Office unified access: catalog/binding access API and cross-axis."""

from __future__ import annotations

import pytest

from tests.office.access_helpers import (
    create_nested_catalog,
    create_private_catalog,
    create_public_catalog,
    enable_catalog_link,
    enable_document_link,
    extract_public_token,
    patch_access_members,
    upload_txt_document,
)

pytestmark = [pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_catalog_access_owner_get_returns_defaults(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    response = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resource_kind"] == "catalog"
    assert body["resource_id"] == catalog_id
    assert body["link_enabled"] is False
    assert isinstance(body["members"], list)


@pytest.mark.asyncio
async def test_catalog_access_non_owner_get_forbidden(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    response = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system_user2,
    )
    assert response.status_code == 403
    body = response.json()
    assert body.get("code") == "authz_denied"


@pytest.mark.asyncio
async def test_catalog_access_missing_catalog_returns_forbidden_for_non_owner(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    fake_catalog_id = f"missing_catalog_{unique_id}"
    response = await office_client.get(
        f"/documents/api/v1/catalogs/{fake_catalog_id}/access",
        headers=auth_headers_system,
    )
    assert response.status_code == 403
    assert response.json().get("code") == "authz_denied"


@pytest.mark.asyncio
async def test_catalog_access_patch_company_visible_private_blocks_peer(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_public_catalog(office_client, auth_headers_system, unique_id)
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"company_visible": False},
    )
    assert patch.status_code == 200
    assert patch.json()["company_visible"] is False

    blocked = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_catalog_access_patch_company_visible_public_allows_peer(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"company_visible": True},
    )
    assert patch.status_code == 200
    assert patch.json()["company_visible"] is True

    ok = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_catalog_access_patch_link_enabled_returns_public_url(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": True, "link_permission": "viewer"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["link_enabled"] is True
    assert isinstance(body["public_url"], str)
    assert "/documents/p/" in body["public_url"]


@pytest.mark.asyncio
async def test_catalog_access_disable_link_invalidates_token(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    disable = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": False},
    )
    assert disable.status_code == 200
    assert disable.json()["link_enabled"] is False

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 404


@pytest.mark.asyncio
async def test_catalog_access_patch_link_permission_edit_reflected_in_resolve(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    token, _body = await enable_catalog_link(
        office_client,
        auth_headers_system,
        catalog_id,
        link_permission="editor",
    )
    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
    assert resolve.json()["link_permission"] == "editor"


@pytest.mark.asyncio
async def test_catalog_access_patch_members_grants_peer_access(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    patch = await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{catalog_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    member_ids = {row["user_id"] for row in patch["members"]}
    assert system_user2_id in member_ids

    ok = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_catalog_access_patch_members_on_public_catalog_rejected(
    office_client,
    frontend_client,
    auth_headers_system,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_public_catalog(office_client, auth_headers_system, unique_id)
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"members": [{"user_id": system_user2_id, "relation": "viewer"}]},
    )
    assert patch.status_code == 400
    detail = (patch.json().get("detail") or "").lower()
    assert "company-visible" in detail or "компании" in detail


@pytest.mark.asyncio
async def test_catalog_access_rotate_without_link_rejected(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    rotate = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/access/link/rotate",
        headers=auth_headers_system,
    )
    assert rotate.status_code == 400


@pytest.mark.asyncio
async def test_catalog_access_rotate_invalidates_old_token(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    old_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    rotate = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/access/link/rotate",
        headers=auth_headers_system,
    )
    assert rotate.status_code == 200, rotate.text
    new_token = extract_public_token(rotate.json()["public_url"])
    assert new_token != old_token

    old_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{old_token}")
    assert old_resolve.status_code == 404


@pytest.mark.asyncio
async def test_catalog_access_reenable_link_preserves_token_hash(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    first_patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": True, "link_permission": "viewer"},
    )
    assert first_patch.status_code == 200
    token = extract_public_token(first_patch.json()["public_url"])

    second_patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": True},
    )
    assert second_patch.status_code == 200

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200


@pytest.mark.asyncio
async def test_binding_access_owner_get_returns_viewer_scope(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"bind-access-{unique_id}",
    )
    response = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    assert response.json()["resource_kind"] == "binding"


@pytest.mark.asyncio
async def test_binding_access_catalog_member_can_get(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{catalog_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"cat-member-{unique_id}",
    )
    response = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_binding_access_binding_only_member_can_get_not_catalog_access(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"bind-only-{unique_id}",
    )
    await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/documents/{file_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )

    binding_get = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
    )
    assert binding_get.status_code == 200

    catalog_get = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system_user2,
    )
    assert catalog_get.status_code == 403


@pytest.mark.asyncio
async def test_binding_access_peer_without_access_forbidden(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"no-access-{unique_id}",
    )
    response = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_binding_access_patch_link_enable_returns_public_url(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{catalog_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"link-enable-{unique_id}",
    )
    patch = await office_client.patch(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
        json={"link_enabled": True, "link_permission": "viewer"},
    )
    assert patch.status_code == 200
    assert isinstance(patch.json()["public_url"], str)


@pytest.mark.asyncio
async def test_binding_access_patch_members_sync(
    office_client,
    frontend_client,
    auth_headers_system,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"members-sync-{unique_id}",
    )
    add = await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/documents/{file_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    add_ids = {row["user_id"] for row in add["members"]}
    assert system_user2_id in add_ids

    remove = await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/documents/{file_id}/access",
        members=[],
    )
    remove_ids = {row["user_id"] for row in remove["members"]}
    assert system_user2_id not in remove_ids


@pytest.mark.asyncio
async def test_binding_access_patch_link_permission_edit(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"edit-perm-{unique_id}",
    )
    token, _body = await enable_document_link(
        office_client,
        auth_headers_system,
        file_id,
        link_permission="editor",
    )
    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
    assert resolve.json()["link_permission"] == "editor"


@pytest.mark.asyncio
async def test_binding_access_rotate_invalidates_old_token(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"bind-rotate-{unique_id}",
    )
    old_token, _body = await enable_document_link(office_client, auth_headers_system, file_id)

    rotate = await office_client.post(
        f"/documents/api/v1/documents/{file_id}/access/link/rotate",
        headers=auth_headers_system,
    )
    assert rotate.status_code == 200
    new_token = extract_public_token(rotate.json()["public_url"])
    assert new_token != old_token

    old_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{old_token}")
    assert old_resolve.status_code == 404


@pytest.mark.asyncio
async def test_binding_access_non_member_patch_forbidden(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"patch-denied-{unique_id}",
    )
    patch = await office_client.patch(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
        json={"link_enabled": True},
    )
    assert patch.status_code == 403


@pytest.mark.asyncio
async def test_binding_access_soft_deleted_binding_not_found(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"soft-del-{unique_id}",
    )
    delete_response = await office_client.delete(
        f"/documents/api/v1/documents/{file_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    get_access = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system,
    )
    assert get_access.status_code == 404


@pytest.mark.asyncio
async def test_cross_axis_private_catalog_binding_public_link_anonymous_open(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"cross-private-{unique_id}",
    )
    token, _body = await enable_document_link(office_client, auth_headers_system, file_id)

    get_access = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system,
    )
    assert get_access.status_code == 200
    assert get_access.json()["company_visible"] is False

    open_response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert open_response.status_code == 200


@pytest.mark.asyncio
async def test_cross_axis_public_catalog_binding_without_link_hidden_in_browse(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_public_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"no-link-{unique_id}",
    )
    peer_list = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert peer_list.status_code == 200

    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)
    items = await office_client.get(f"/documents/api/v1/public/catalog/{catalog_token}/items")
    assert items.status_code == 200
    listed_ids = {row["file_id"] for row in items.json()["items"]}
    assert file_id not in listed_ids


@pytest.mark.asyncio
async def test_cross_axis_catalog_and_binding_tokens_resolve_different_kinds(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"dual-link-{unique_id}",
    )
    binding_token, _body = await enable_document_link(office_client, auth_headers_system, file_id)
    catalog_token, _body2 = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    binding_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{binding_token}")
    assert binding_resolve.status_code == 200
    assert binding_resolve.json()["resource_kind"] == "binding"

    catalog_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{catalog_token}")
    assert catalog_resolve.status_code == 200
    assert catalog_resolve.json()["resource_kind"] == "catalog"
    assert catalog_resolve.json()["file_id"] is None


@pytest.mark.asyncio
async def test_cross_axis_disable_catalog_link_binding_token_still_works(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"cat-off-{unique_id}",
    )
    binding_token, _body = await enable_document_link(office_client, auth_headers_system, file_id)
    catalog_token, _body2 = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    disable = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": False},
    )
    assert disable.status_code == 200

    catalog_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{catalog_token}")
    assert catalog_resolve.status_code == 404

    binding_open = await office_client.get(f"/documents/api/v1/public/open/{binding_token}")
    assert binding_open.status_code == 200


@pytest.mark.asyncio
async def test_cross_axis_disable_binding_link_removed_from_catalog_items(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"bind-off-{unique_id}",
    )
    await enable_document_link(office_client, auth_headers_system, file_id)
    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    items_before = await office_client.get(f"/documents/api/v1/public/catalog/{catalog_token}/items")
    assert file_id in {row["file_id"] for row in items_before.json()["items"]}

    disable = await office_client.patch(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": False},
    )
    assert disable.status_code == 200

    items_after = await office_client.get(f"/documents/api/v1/public/catalog/{catalog_token}/items")
    assert file_id not in {row["file_id"] for row in items_after.json()["items"]}


@pytest.mark.asyncio
async def test_cross_axis_nested_public_parent_allows_peer_list_child_docs(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    parent_id = await create_public_catalog(office_client, auth_headers_system, unique_id)
    child_id = await create_nested_catalog(
        office_client,
        auth_headers_system,
        unique_id,
        parent_catalog_id=parent_id,
        company_visible=False,
    )
    await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=child_id,
        title=f"nested-child-{unique_id}",
    )
    peer_list = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": child_id},
        headers=auth_headers_system_user2,
    )
    assert peer_list.status_code == 200


@pytest.mark.asyncio
async def test_cross_axis_nested_catalog_peer_without_binding_membership_forbidden(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    parent_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    child_id = await create_nested_catalog(
        office_client,
        auth_headers_system,
        unique_id,
        parent_catalog_id=parent_id,
        company_visible=False,
    )
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=child_id,
        title=f"nested-bind-{unique_id}",
    )

    peer_get = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system_user2,
    )
    assert peer_get.status_code == 403


@pytest.mark.asyncio
async def test_catalog_access_owner_cannot_remove_self_from_members(
    office_client,
    frontend_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    owner_id = (
        await office_client.get(
            f"/documents/api/v1/catalogs/{catalog_id}",
            headers=auth_headers_system,
        )
    ).json()["owner_user_id"]

    patch = await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{catalog_id}/access",
        members=[],
    )
    member_ids = {row["user_id"] for row in patch["members"]}
    assert owner_id not in member_ids
    catalog_still_owned = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system,
    )
    assert catalog_still_owned.status_code == 200


@pytest.mark.asyncio
async def test_catalog_editor_member_can_view_but_not_share_or_admin(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"editor-doc-{unique_id}",
    )
    patch = await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{catalog_id}/access",
        members=[{"user_id": system_user2_id, "relation": "editor"}],
    )
    assert any(
        row["user_id"] == system_user2_id and row["relation"] == "editor"
        for row in patch["members"]
    )

    listed = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": catalog_id},
        headers=auth_headers_system_user2,
    )
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1

    share = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system_user2,
    )
    assert share.status_code == 403
    assert share.json().get("code") == "authz_denied"

    rag = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/rag-index/enable",
        headers=auth_headers_system_user2,
    )
    assert rag.status_code == 403


@pytest.mark.asyncio
async def test_catalog_members_endpoint_uses_relation_canon(
    office_client,
    frontend_client,
    auth_headers_system,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    add = await office_client.post(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
        json={"user_id": system_user2_id, "relation": "editor"},
    )
    assert add.status_code == 200, add.text
    members = add.json()["members"]
    assert any(
        row["user_id"] == system_user2_id and row["relation"] == "editor" for row in members
    )

    listed = await office_client.get(
        f"/documents/api/v1/catalogs/{catalog_id}/members",
        headers=auth_headers_system,
    )
    assert listed.status_code == 200
    assert any(
        row["user_id"] == system_user2_id and row["relation"] == "editor"
        for row in listed.json()["members"]
    )

    remove = await office_client.delete(
        f"/documents/api/v1/catalogs/{catalog_id}/members/{system_user2_id}",
        headers=auth_headers_system,
    )
    assert remove.status_code == 204


@pytest.mark.asyncio
async def test_document_move_rewrites_fga_catalog_inheritance(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    source_id = await create_private_catalog(
        office_client, auth_headers_system, unique_id, title_prefix="move-src"
    )
    target_id = await create_private_catalog(
        office_client, auth_headers_system, unique_id, title_prefix="move-dst"
    )
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=source_id,
        title=f"move-doc-{unique_id}",
    )
    await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/catalogs/{source_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    before = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": source_id},
        headers=auth_headers_system_user2,
    )
    assert before.status_code == 200
    assert file_id in {item["file_id"] for item in before.json()["items"]}

    moved = await office_client.post(
        f"/documents/api/v1/documents/{file_id}/move",
        headers=auth_headers_system,
        json={"catalog_id": target_id},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["catalog_id"] == target_id

    after_source = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": source_id},
        headers=auth_headers_system_user2,
    )
    assert after_source.status_code == 200
    assert file_id not in {item["file_id"] for item in after_source.json()["items"]}

    after_target = await office_client.get(
        "/documents/api/v1/documents",
        params={"catalog_id": target_id},
        headers=auth_headers_system_user2,
    )
    assert after_target.status_code == 403

    peer_doc = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/preview",
        headers=auth_headers_system_user2,
    )
    assert peer_doc.status_code == 403


@pytest.mark.asyncio
async def test_permanent_delete_clears_document_fga_access(
    office_client,
    frontend_client,
    auth_headers_system,
    auth_headers_system_user2,
    system_user2_id,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    file_id = await upload_txt_document(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"purge-doc-{unique_id}",
    )
    await patch_access_members(
        office_client,
        auth_headers_system,
        resource_path=f"/documents/api/v1/documents/{file_id}/access",
        members=[{"user_id": system_user2_id, "relation": "viewer"}],
    )
    peer_before = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/preview",
        headers=auth_headers_system_user2,
    )
    assert peer_before.status_code == 200

    soft = await office_client.delete(
        f"/documents/api/v1/documents/{file_id}",
        headers=auth_headers_system,
    )
    assert soft.status_code == 204
    permanent = await office_client.delete(
        f"/documents/api/v1/documents/{file_id}/permanent",
        headers=auth_headers_system,
    )
    assert permanent.status_code == 204, permanent.text

    peer_after = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/preview",
        headers=auth_headers_system_user2,
    )
    assert peer_after.status_code == 404

    owner_after = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/preview",
        headers=auth_headers_system,
    )
    assert owner_after.status_code == 404

    owner_access = await office_client.get(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=auth_headers_system,
    )
    assert owner_access.status_code == 404
