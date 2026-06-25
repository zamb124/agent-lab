"""Негативные сценарии Files API."""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from tests.sync.api._helpers import platform_auxiliary_file_spec_json
from tests.sync.integration.conftest import _temporary_settings


@pytest.mark.asyncio
async def test_upload_empty_file_400(
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=sync_auth_headers,
        data={"spec": platform_auxiliary_file_spec_json()},
        files=files,
    )
    assert r.status_code == 400, r.text
    assert "Пустой" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_file_metadata_404(
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await frontend_client.get(
        "/frontend/api/v1/files/ffffffffffffffffffffffffffffffff",
        headers=sync_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_returns_503_when_s3_disabled(
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    from apps.frontend.main import app

    async with _temporary_settings({"s3.enabled": False}):
        files = {"file": ("x.txt", io.BytesIO(b"data"), "text/plain")}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.post(
                "/frontend/api/v1/files/",
                headers=sync_auth_headers,
                data={"spec": platform_auxiliary_file_spec_json()},
                files=files,
            )
    assert r.status_code == 503
    assert "S3" in r.json()["detail"]
