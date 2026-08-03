"""Public search guest JWT → chunked Files API (без base64 / single-shot)."""

from __future__ import annotations

import hashlib

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from core.utils.tokens import TokenType, get_token_service
from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)


def _unique_client_ip(unique_id: str) -> str:
    digest = hashlib.sha256(unique_id.encode("utf-8")).digest()
    return f"10.{digest[0]}.{digest[1]}.{digest[2]}"


def _session_headers() -> dict[str, str]:
    return {
        "origin": "http://testserver",
        "referer": "http://testserver/search",
    }


@pytest_asyncio.fixture
async def public_search_client(frontend_app, unique_id):
    transport = ASGITransport(app=frontend_app, client=(_unique_client_ip(unique_id), 12345))
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_public_search_guest_chunked_upload_and_download(
    public_search_client: AsyncClient,
    unique_id: str,
):
    session_response = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=_session_headers(),
        json={
            "mode": "quick",
            "origin": "http://testserver",
            "expires_in_seconds": 300,
            "consume_search_quota": True,
        },
    )
    assert session_response.status_code == 200, session_response.text
    session = session_response.json()
    token = session["token"]
    assert session["token_type"] == "Bearer"
    token_data = get_token_service().validate_token(token)
    assert token_data is not None
    assert token_data.token_type == TokenType.EMBED_SESSION
    assert token_data.user_id.startswith("search_guest_")

    payload = f"public-search-chunked-{unique_id}\n".encode("utf-8")
    auth_headers = {"Authorization": f"Bearer {token}"}
    upload = await chunked_upload_file(
        public_search_client,
        auth_headers,
        content=payload,
        original_name=f"search-{unique_id}.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
        files_api_prefix="/frontend/api/v1/files",
    )
    assert upload.status_code == 200, upload.text
    body = upload.json()
    file_id = body["file_id"]
    assert isinstance(file_id, str) and file_id != ""
    download_url = body["url"]
    assert isinstance(download_url, str)
    assert "/api/v1/files/download/" in download_url
    assert file_id in download_url

    downloaded = await public_search_client.get(
        f"/frontend/api/v1/files/download/{file_id}",
        headers=auth_headers,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content == payload


@pytest.mark.asyncio
async def test_public_search_guest_cannot_use_single_shot_files_post(
    public_search_client: AsyncClient,
):
    session_response = await public_search_client.post(
        "/frontend/api/public/search/session",
        headers=_session_headers(),
        json={
            "mode": "quick",
            "origin": "http://testserver",
            "expires_in_seconds": 300,
            "consume_search_quota": False,
        },
    )
    assert session_response.status_code == 200, session_response.text
    token = session_response.json()["token"]

    response = await public_search_client.post(
        "/frontend/api/v1/files/",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("x.txt", b"no-single-shot", "text/plain")},
        data={"spec": platform_auxiliary_upload_spec_json()},
    )
    assert response.status_code in {404, 405}, response.text
