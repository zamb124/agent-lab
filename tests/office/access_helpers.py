"""Shared helpers for Office unified access integration tests."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from httpx import AsyncClient

from tests.office.helpers import upload_office_file_bytes

OfficeLinkPermission = Literal["viewer", "editor"]
OfficeMemberRelation = Literal["viewer", "editor"]


def parse_viz_stream_url(editor_config: dict[str, object]) -> str:
    viz = editor_config.get("viz")
    if not isinstance(viz, dict):
        raise AssertionError("editor-config: viz payload required")
    stream_url = viz.get("stream_url")
    if not isinstance(stream_url, str) or stream_url == "":
        raise AssertionError("editor-config: viz.stream_url required")
    return stream_url


async def create_private_catalog(
    office_client: AsyncClient,
    headers: dict[str, str],
    unique_id: str,
    *,
    title_prefix: str = "access-private",
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={"title": f"{title_prefix}-{unique_id}", "company_visible": False},
    )
    assert response.status_code == 200, response.text
    return response.json()["catalog_id"]


async def create_public_catalog(
    office_client: AsyncClient,
    headers: dict[str, str],
    unique_id: str,
    *,
    title_prefix: str = "access-public",
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={"title": f"{title_prefix}-{unique_id}", "company_visible": True},
    )
    assert response.status_code == 200, response.text
    return response.json()["catalog_id"]


async def create_nested_catalog(
    office_client: AsyncClient,
    headers: dict[str, str],
    unique_id: str,
    *,
    parent_catalog_id: str,
    company_visible: bool = False,
    title_prefix: str = "access-nested",
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={
            "title": f"{title_prefix}-{unique_id}",
            "company_visible": company_visible,
            "parent_catalog_id": parent_catalog_id,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["catalog_id"]


async def upload_txt_document(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    catalog_id: str,
    title: str,
    content: bytes = b"public-access-test",
    namespace: str = "default",
) -> str:
    file_payload = await upload_office_file_bytes(
        office_client,
        headers,
        filename=f"{title}.txt",
        content=content,
        content_type="text/plain",
        namespace=namespace,
    )
    file_id = file_payload["file_id"]
    if not isinstance(file_id, str) or file_id == "":
        raise AssertionError("upload_txt_document: file_id required")
    bind = await office_client.post(
        "/documents/api/v1/documents",
        headers=headers,
        json={"file_id": file_id, "title": title, "catalog_id": catalog_id},
    )
    assert bind.status_code == 200, bind.text
    return bind.json()["file_id"]


async def upload_json_document(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    catalog_id: str,
    title: str,
    content: bytes = b'{"access":"test"}',
    namespace: str = "default",
) -> str:
    file_payload = await upload_office_file_bytes(
        office_client,
        headers,
        filename=f"{title}.json",
        content=content,
        content_type="application/json",
        namespace=namespace,
    )
    file_id = file_payload["file_id"]
    if not isinstance(file_id, str) or file_id == "":
        raise AssertionError("upload_json_document: file_id required")
    bind = await office_client.post(
        "/documents/api/v1/documents",
        headers=headers,
        json={"file_id": file_id, "title": title, "catalog_id": catalog_id},
    )
    assert bind.status_code == 200, bind.text
    return bind.json()["file_id"]


def extract_public_token(public_url: str) -> str:
    path = urlparse(public_url).path
    match = re.search(r"/documents/p/([^/]+)$", path)
    assert match is not None
    return match.group(1)


def extract_query_token(url: str) -> str:
    query = urlparse(url).query
    for part in query.split("&"):
        if part.startswith("token="):
            token = part.removeprefix("token=")
            if token == "":
                raise AssertionError(f"empty token in url: {url}")
            return token
    raise AssertionError(f"token query param required in url: {url}")


def parse_download_url(open_body: dict[str, object]) -> str:
    download_url = open_body.get("download_url")
    if not isinstance(download_url, str) or download_url == "":
        raise AssertionError("public open: download_url required")
    return download_url


def parse_text_stream_url(open_body: dict[str, object]) -> str:
    text = open_body.get("text")
    if not isinstance(text, dict):
        raise AssertionError("public open: text payload required")
    stream_url = text.get("stream_url")
    if not isinstance(stream_url, str) or stream_url == "":
        raise AssertionError("public open: text.stream_url required")
    return stream_url


def parse_text_save_url(open_body: dict[str, object]) -> str:
    text = open_body.get("text")
    if not isinstance(text, dict):
        raise AssertionError("public open: text payload required")
    save_url = text.get("save_url")
    if not isinstance(save_url, str) or save_url == "":
        raise AssertionError("public open: text.save_url required")
    return save_url


async def public_open(office_client: AsyncClient, token: str) -> dict[str, object]:
    response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert response.status_code == 200, response.text
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("public open: JSON object required")
    return body


async def enable_catalog_link(
    office_client: AsyncClient,
    headers: dict[str, str],
    catalog_id: str,
    *,
    link_permission: OfficeLinkPermission = "viewer",
) -> tuple[str, dict[str, object]]:
    response = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": link_permission},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    public_url = body["public_url"]
    assert isinstance(public_url, str) and public_url
    return extract_public_token(public_url), body


async def enable_document_link(
    office_client: AsyncClient,
    headers: dict[str, str],
    file_id: str,
    *,
    link_permission: OfficeLinkPermission = "viewer",
) -> tuple[str, dict[str, object]]:
    response = await office_client.patch(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": link_permission},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    public_url = body["public_url"]
    assert isinstance(public_url, str) and public_url
    return extract_public_token(public_url), body


async def patch_access_members(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    resource_path: str,
    members: list[dict[str, str]],
) -> dict[str, object]:
    response = await office_client.patch(
        resource_path,
        headers=headers,
        json={"members": members},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    if not isinstance(body, dict):
        raise AssertionError("patch access: JSON object required")
    return body
