"""Office unified access — legacy POST /documents/{id}/shares wrapper."""

from __future__ import annotations

import pytest

from tests.office.access_helpers import (
    create_private_catalog,
    enable_binding_link,
    extract_public_token,
    upload_txt_binding,
)

pytestmark = [pytest.mark.timeout(120)]


@pytest.mark.asyncio
async def test_legacy_share_create_returns_documents_p_url(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"legacy-share-{unique_id}",
    )
    response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system,
        json={"permission": "view"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert "/documents/p/" in body["share_url"]
    assert "/api/v1/shares/" not in body["share_url"]


@pytest.mark.asyncio
async def test_legacy_share_second_create_rotates_token(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"legacy-rotate-{unique_id}",
    )
    first = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system,
        json={"permission": "view"},
    )
    assert first.status_code == 200
    old_token = extract_public_token(first.json()["share_url"])

    second = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system,
        json={"permission": "view"},
    )
    assert second.status_code == 200
    new_token = extract_public_token(second.json()["share_url"])
    assert new_token != old_token

    old_resolve = await office_client.get(f"/documents/api/v1/public/resolve/{old_token}")
    assert old_resolve.status_code == 404


@pytest.mark.asyncio
async def test_legacy_share_edit_permission_reflected_in_resolve(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"legacy-edit-{unique_id}",
    )
    response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system,
        json={"permission": "edit"},
    )
    assert response.status_code == 200
    token = extract_public_token(response.json()["share_url"])

    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
    assert resolve.json()["link_permission"] == "edit"


@pytest.mark.asyncio
async def test_legacy_share_create_without_access_forbidden(
    office_client,
    auth_headers_system,
    auth_headers_system_user2,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"legacy-denied-{unique_id}",
    )
    response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system_user2,
        json={"permission": "view"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_legacy_share_after_access_enable_still_works(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"legacy-enabled-{unique_id}",
    )
    await enable_binding_link(office_client, auth_headers_system, binding_id)

    response = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/shares",
        headers=auth_headers_system,
        json={"permission": "view"},
    )
    assert response.status_code == 200
    token = extract_public_token(response.json()["share_url"])
    resolve = await office_client.get(f"/documents/api/v1/public/resolve/{token}")
    assert resolve.status_code == 200
