"""Shared helpers for Office unified access integration tests."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from httpx import AsyncClient

from tests.office.helpers import upload_office_file_bytes

OfficeLinkPermission = Literal["view", "edit"]


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
        json={"title": f"{title_prefix}-{unique_id}", "is_public": False},
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
        json={"title": f"{title_prefix}-{unique_id}", "is_public": True},
    )
    assert response.status_code == 200, response.text
    return response.json()["catalog_id"]


async def create_nested_catalog(
    office_client: AsyncClient,
    headers: dict[str, str],
    unique_id: str,
    *,
    parent_catalog_id: str,
    is_public: bool = False,
    title_prefix: str = "access-nested",
) -> str:
    response = await office_client.post(
        "/documents/api/v1/catalogs",
        headers=headers,
        json={
            "title": f"{title_prefix}-{unique_id}",
            "is_public": is_public,
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


async def enable_catalog_link(
    office_client: AsyncClient,
    headers: dict[str, str],
    catalog_id: str,
    *,
    permission: OfficeLinkPermission = "view",
) -> tuple[str, dict[str, object]]:
    response = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": permission},
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
    permission: OfficeLinkPermission = "view",
) -> tuple[str, dict[str, object]]:
    response = await office_client.patch(
        f"/documents/api/v1/documents/{file_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": permission},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    public_url = body["public_url"]
    assert isinstance(public_url, str) and public_url
    return extract_public_token(public_url), body
