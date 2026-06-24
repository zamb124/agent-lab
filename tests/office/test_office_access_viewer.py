"""Office unified access — anonymous viewer-stream/frame/save and office-download."""

from __future__ import annotations

import time
from urllib.parse import quote, urlparse, urlunparse

import jwt
import pytest

from apps.office.config import get_office_settings
from tests.office.access_helpers import (
    create_private_catalog,
    enable_binding_link,
    extract_query_token,
    parse_download_url,
    parse_text_save_url,
    parse_text_stream_url,
    public_open,
    upload_json_binding,
    upload_txt_binding,
)

pytestmark = [pytest.mark.timeout(120)]

UPLOAD_CONTENT = b"office-access-download-bytes"


@pytest.mark.asyncio
async def test_public_open_download_url_returns_file_bytes(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"download-{unique_id}",
        content=UPLOAD_CONTENT,
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    download_url = parse_download_url(open_body)

    download_response = await office_client.get(download_url)
    assert download_response.status_code == 200
    assert download_response.content == UPLOAD_CONTENT


@pytest.mark.asyncio
async def test_public_open_view_permission_stream_without_save_url(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"view-stream-{unique_id}",
        content=UPLOAD_CONTENT,
    )
    token, _body = await enable_binding_link(
        office_client,
        auth_headers_system,
        binding_id,
        link_permission="view",
    )
    open_body = await public_open(office_client, token)
    text_payload = open_body.get("text")
    assert isinstance(text_payload, dict)
    assert text_payload.get("edit_mode") is False
    assert text_payload.get("save_url") == ""

    stream_url = parse_text_stream_url(open_body)
    stream_response = await office_client.get(stream_url)
    assert stream_response.status_code == 200
    assert stream_response.content == UPLOAD_CONTENT


@pytest.mark.asyncio
async def test_public_open_view_permission_viewer_save_forbidden(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"view-save-{unique_id}",
    )
    token, _body = await enable_binding_link(
        office_client,
        auth_headers_system,
        binding_id,
        link_permission="edit",
    )
    open_body = await public_open(office_client, token)
    save_url = parse_text_save_url(open_body)

    downgrade = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=auth_headers_system,
        json={"link_permission": "view"},
    )
    assert downgrade.status_code == 200

    save_response = await office_client.post(save_url, content=b"tampered")
    assert save_response.status_code == 403
    assert "запрещено" in (save_response.json().get("detail") or "").lower()


@pytest.mark.asyncio
async def test_public_open_edit_permission_viewer_save_updates_content(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"edit-save-{unique_id}",
        content=b"before-content",
    )
    token, _body = await enable_binding_link(
        office_client,
        auth_headers_system,
        binding_id,
        link_permission="edit",
    )
    open_body = await public_open(office_client, token)
    save_url = parse_text_save_url(open_body)
    new_content = b"after-content-by-guest"

    save_response = await office_client.post(save_url, content=new_content)
    assert save_response.status_code == 204

    stream_url = parse_text_stream_url(open_body)
    stream_response = await office_client.get(stream_url)
    assert stream_response.status_code == 200
    assert stream_response.content == new_content


@pytest.mark.asyncio
async def test_viewer_stream_without_token_unprocessable(
    office_client,
):
    response = await office_client.get("/documents/api/v1/viewer-stream")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_viewer_stream_bad_jwt_unauthorized(
    office_client,
):
    response = await office_client.get("/documents/api/v1/viewer-stream?token=not-a-jwt")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_viewer_stream_old_token_after_rotate_forbidden(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"rotate-stream-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    old_stream_url = parse_text_stream_url(open_body)

    rotate = await office_client.post(
        f"/documents/api/v1/documents/{binding_id}/access/link/rotate",
        headers=auth_headers_system,
    )
    assert rotate.status_code == 200

    old_stream = await office_client.get(old_stream_url)
    assert old_stream.status_code == 403


@pytest.mark.asyncio
async def test_viewer_frame_returns_html_with_stream_url(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"frame-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    stream_url = parse_text_stream_url(open_body)
    stream_token = extract_query_token(stream_url)

    frame_response = await office_client.get(
        f"/documents/api/v1/viewer-frame?token={quote(stream_token, safe='')}",
    )
    assert frame_response.status_code == 200
    assert "text/html" in frame_response.headers.get("content-type", "")
    assert stream_token in frame_response.text or "viewer-stream" in frame_response.text


@pytest.mark.asyncio
async def test_viewer_stream_tampered_file_id_forbidden(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_json_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"tamper-{unique_id}",
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    stream_url = parse_text_stream_url(open_body)
    stream_token = extract_query_token(stream_url)

    secret = get_office_settings().office.jwt_secret
    payload = jwt.decode(stream_token, secret, algorithms=["HS256"])
    payload["file_id"] = "file_tampered_id"
    payload["iat"] = int(time.time())
    payload["exp"] = int(time.time()) + 120
    tampered_token = jwt.encode(payload, secret, algorithm="HS256")

    parsed = urlparse(stream_url)
    tampered_query = f"token={quote(tampered_token, safe='')}"
    tampered_url = urlunparse(parsed._replace(query=tampered_query))
    response = await office_client.get(tampered_url)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_office_download_after_soft_delete_binding_still_allowed_regression(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"dl-delete-{unique_id}",
        content=UPLOAD_CONTENT,
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    download_url = parse_download_url(open_body)

    delete_response = await office_client.delete(
        f"/documents/api/v1/documents/{binding_id}",
        headers=auth_headers_system,
    )
    assert delete_response.status_code == 204

    download_response = await office_client.get(download_url)
    assert download_response.status_code == 200
    assert download_response.content == UPLOAD_CONTENT


@pytest.mark.asyncio
async def test_office_download_still_works_after_link_disabled_regression(
    office_client,
    auth_headers_system,
    unique_id,
):
    catalog_id = await create_private_catalog(office_client, auth_headers_system, unique_id)
    binding_id = await upload_txt_binding(
        office_client,
        auth_headers_system,
        catalog_id=catalog_id,
        title=f"dl-disabled-{unique_id}",
        content=UPLOAD_CONTENT,
    )
    token, _body = await enable_binding_link(office_client, auth_headers_system, binding_id)
    open_body = await public_open(office_client, token)
    download_url = parse_download_url(open_body)

    disable = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=auth_headers_system,
        json={"link_enabled": False},
    )
    assert disable.status_code == 200

    download_response = await office_client.get(download_url)
    assert download_response.status_code == 200
    assert download_response.content == UPLOAD_CONTENT
