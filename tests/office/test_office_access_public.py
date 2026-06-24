"""Office unified access and public preview — anonymous public API."""

from __future__ import annotations

import pytest

from tests.office.access_helpers import (
    create_private_catalog,
    enable_binding_link,
    enable_catalog_link,
    extract_public_token,
    upload_txt_binding,
)

pytestmark = [pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_patch_binding_access_enables_public_link(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"access-binding-{unique_id}",
    )
    patch = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": True, "link_permission": "view"},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    assert body["link_enabled"] is True
    assert body["link_permission"] == "view"
    assert isinstance(body["public_url"], str)
    assert "/documents/p/" in body["public_url"]


@pytest.mark.asyncio
async def test_public_file_open_without_session(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"public-open-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
    resolve_body = resolve.json()
    assert resolve_body["resource_kind"] == "binding"
    assert resolve_body["binding_id"] == binding_id

    open_response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert open_response.status_code == 200, open_response.text
    open_body = open_response.json()
    assert open_body["binding_id"] == binding_id
    assert isinstance(open_body.get("download_url"), str)
    assert open_body["download_url"].startswith("http")


@pytest.mark.asyncio
async def test_rotate_link_invalidates_old_token(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"rotate-link-{unique_id}",
    )
    old_token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)

    rotate = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/access/link/rotate",
        headers=auth_headers_system,
    )
    assert rotate.status_code == 200, rotate.text
    new_token = extract_public_token(rotate.json()["public_url"])
    assert new_token != old_token

    old_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{old_token}")
    assert old_resolve.status_code == 404

    new_open = await office_client.get(f"/documents/api/v1/public/open/{new_token}")
    assert new_open.status_code == 200


@pytest.mark.asyncio
async def test_public_catalog_hides_binding_without_own_link(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    visible_binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"visible-{unique_id}",
    )
    hidden_binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"hidden-{unique_id}",
    )
    await enable_binding_link(office_client, auth_headers_system, visible_binding_id)
    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    items = await office_client.get(f"/documents/api/v1/public/catalog/{catalog_token}/items")
    assert items.status_code == 200
    listed_ids = {row["binding_id"] for row in items.json()["items"]}
    assert visible_binding_id in listed_ids
    assert hidden_binding_id not in listed_ids


@pytest.mark.asyncio
async def test_public_catalog_binding_open_without_session(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"catalog-open-{unique_id}",
    )
    await enable_binding_link(office_client, auth_headers_system, binding_id)
    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    open_response = await office_client.get(
        f"/documents/api/v1/public/catalog/{catalog_token}/bindings/{binding_id}/open",
    )
    assert open_response.status_code == 200, open_response.text
    open_body = open_response.json()
    assert open_body["binding_id"] == binding_id
    assert isinstance(open_body.get("download_url"), str)


@pytest.mark.asyncio
async def test_get_binding_access_reflects_catalog_company_visibility(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"member-access-{unique_id}",
    )
    get_access = await office_client.get(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=auth_headers_system,
    )
    assert get_access.status_code == 200
    assert get_access.json()["company_visible"] is False


@pytest.mark.asyncio
async def test_public_resolve_catalog_token_returns_catalog_kind(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
    body = resolve.json()
    assert body["resource_kind"] == "catalog"
    assert body["file_id"] is None
    assert body["catalog_id"] == catalog_id


@pytest.mark.asyncio
async def test_public_resolve_garbage_token_not_found(
    office_client,
    unique_id,
):
    response = await office_client.get(f"/documents/api/v1/public/resolve/not-a-valid-token-{unique_id}")
    assert response.status_code == 404
    assert "найдена" in (response.json().get("detail") or "").lower()


@pytest.mark.asyncio
async def test_public_open_catalog_token_rejected(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    open_response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert open_response.status_code == 400
    assert "прямой" in (open_response.json().get("detail") or "").lower()


@pytest.mark.asyncio
async def test_public_catalog_items_with_binding_token_rejected(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"wrong-token-{unique_id}",
    )
    binding_token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)

    items = await office_client.get(f"/documents/api/v1/public/catalog/{binding_token}/items")
    assert items.status_code == 400
    assert "каталог" in (items.json().get("detail") or "").lower()


@pytest.mark.asyncio
async def test_public_catalog_binding_open_wrong_binding_id_not_found(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"wrong-bind-{unique_id}",
    )
    await enable_binding_link(office_client, auth_headers_system, binding_id)
    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    fake_binding_id = f"missing_binding_{unique_id}"
    open_response = await office_client.get(
        f"/documents/api/v1/public/catalog/{catalog_token}/bindings/{fake_binding_id}/open",
    )
    assert open_response.status_code == 404


@pytest.mark.asyncio
async def test_public_catalog_binding_open_without_binding_link_not_found(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"no-bind-link-{unique_id}",
    )
    catalog_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    open_response = await office_client.get(
        f"/documents/api/v1/public/catalog/{catalog_token}/bindings/{binding_id}/open",
    )
    assert open_response.status_code == 404


@pytest.mark.asyncio
async def test_public_catalog_binding_open_binding_from_other_catalog_not_found(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_a = await create_private_catalog(
        office_client,
        auth_headers_system,
        unique_id,
        title_prefix="cat-a",
    )
    catalog_b = await create_private_catalog(
        office_client,
        auth_headers_system,
        unique_id,
        title_prefix="cat-b",
    )
    binding_in_b = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_b,
        title=f"other-cat-{unique_id}",
    )
    await enable_binding_link(office_client, auth_headers_system, binding_in_b)
    catalog_a_token, _body = await enable_catalog_link(office_client, auth_headers_system, catalog_a)

    open_response = await office_client.get(
        f"/documents/api/v1/public/catalog/{catalog_a_token}/bindings/{binding_in_b}/open",
    )
    assert open_response.status_code == 404


@pytest.mark.asyncio
async def test_public_open_soft_deleted_binding_not_found(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"deleted-open-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)

    delete_response = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    open_response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert open_response.status_code == 404


@pytest.mark.asyncio
async def test_public_routes_work_without_authorization_header(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"anon-{unique_id}",
    )
    binding_token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    catalog_token, _body2 = await enable_catalog_link(office_client, auth_headers_system, catalog_id)

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{binding_token}")
    assert resolve.status_code == 200

    open_binding = await office_client.get(f"/documents/api/v1/public/open/{binding_token}")
    assert open_binding.status_code == 200

    items = await office_client.get(f"/documents/api/v1/public/catalog/{catalog_token}/items")
    assert items.status_code == 200

    catalog_open = await office_client.get(
        f"/documents/api/v1/public/catalog/{catalog_token}/bindings/{binding_id}/open",
    )
    assert catalog_open.status_code == 200


@pytest.mark.asyncio
async def test_access_routes_require_authentication(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"auth-req-{unique_id}",
    )

    catalog_get = await office_client.get(f"/documents/api/v1/catalogs/{catalog_id}/access")
    assert catalog_get.status_code == 401

    binding_get = await office_client.get(f"/documents/api/v1/documents/{binding_id}/access")
    assert binding_get.status_code == 401


@pytest.mark.asyncio
async def test_public_open_after_disable_link_not_found(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"disabled-open-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)

    disable = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": False},
    )
    assert disable.status_code == 200

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 404

    open_response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert open_response.status_code == 404


@pytest.mark.asyncio
async def test_catalog_access_peer_patch_forbidden(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=auth_headers_system_user2,
        json={"link_enabled": True},
    )
    assert patch.status_code == 403
