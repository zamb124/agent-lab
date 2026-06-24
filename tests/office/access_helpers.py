"""Shared helpers for Office unified access integration tests."""

from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

from httpx import AsyncClient

OfficeLinkPermission = Literal["view", "edit"]


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


async def upload_txt_binding(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    catalog_id: str,
    title: str,
    content: bytes = b"public-access-test",
) -> str:
    upload = await office_client.post(
        "/documents/api/v1/documents",
        headers=headers,
        files={"file": (f"{title}.txt", content, "text/plain")},
        data={"title": title, "catalog_id": catalog_id},
    )
    assert upload.status_code == 200, upload.text
    return upload.json()["binding_id"]


async def upload_json_binding(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    catalog_id: str,
    title: str,
    content: bytes = b'{"access":"test"}',
) -> str:
    upload = await office_client.post(
        "/documents/api/v1/documents",
        headers=headers,
        files={"file": (f"{title}.json", content, "application/json")},
        data={"title": title, "catalog_id": catalog_id},
    )
    assert upload.status_code == 200, upload.text
    return upload.json()["binding_id"]


def extract_public_token(public_url: str) -> str:
    path = urlparse(public_url).path
    match = re.search(r"/documents/p/([^/]+)$", path)
    assert match is not None
    return match.group(1)


async def enable_binding_link(
    office_client: AsyncClient,
    headers: dict[str, str],
    binding_id: str,
    *,
    link_permission: OfficeLinkPermission = "view",
) -> tuple[str, dict[str, object]]:
    patch = await office_client.patch(
        f"/documents/api/v1/documents/{binding_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": link_permission},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    public_url = body["public_url"]
    assert isinstance(public_url, str)
    return extract_public_token(public_url), body


async def enable_catalog_link(
    office_client: AsyncClient,
    headers: dict[str, str],
    catalog_id: str,
    *,
    link_permission: OfficeLinkPermission = "view",
) -> tuple[str, dict[str, object]]:
    patch = await office_client.patch(
        f"/documents/api/v1/catalogs/{catalog_id}/access",
        headers=headers,
        json={"link_enabled": True, "link_permission": link_permission},
    )
    assert patch.status_code == 200, patch.text
    body = patch.json()
    public_url = body["public_url"]
    assert isinstance(public_url, str)
    return extract_public_token(public_url), body


async def public_open(office_client: AsyncClient, token: str) -> dict[str, object]:
    response = await office_client.get(f"/documents/api/v1/public/open/{token}")
    assert response.status_code == 200, response.text
    return response.json()


def parse_download_url(open_body: dict[str, object]) -> str:
    download_url = open_body.get("download_url")
    assert isinstance(download_url, str)
    return download_url


def parse_text_stream_url(open_body: dict[str, object]) -> str:
    assert open_body.get("handler") == "text"
    text_payload = open_body.get("text")
    assert isinstance(text_payload, dict)
    stream_url = text_payload.get("stream_url")
    assert isinstance(stream_url, str)
    return stream_url


def parse_text_save_url(open_body: dict[str, object]) -> str:
    assert open_body.get("handler") == "text"
    text_payload = open_body.get("text")
    assert isinstance(text_payload, dict)
    save_url = text_payload.get("save_url")
    assert isinstance(save_url, str)
    assert save_url != ""
    return save_url


def extract_query_token(url: str, param: str = "token") -> str:
    parsed = urlparse(url)
    query = parsed.query
    for part in query.split("&"):
        if part.startswith(f"{param}="):
            return part.split("=", 1)[1]
    raise AssertionError(f"query param {param} not found in {url}")
