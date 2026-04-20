"""Негативные сценарии Files API."""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient

from tests.sync.integration.conftest import _temporary_settings


@pytest.mark.asyncio
async def test_upload_empty_file_400(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    files = {"file": ("empty.txt", io.BytesIO(b""), "text/plain")}
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files=files,
    )
    assert r.status_code == 400, r.text
    assert "Пустой" in r.json()["detail"]


@pytest.mark.asyncio
async def test_get_file_metadata_404(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await sync_client.get(
        "/sync/api/v1/files/ffffffffffffffffffffffffffffffff",
        headers=sync_auth_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_upload_returns_503_when_s3_disabled(
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    """503 при отключённом S3. Подмена settings через fixture-runtime
    `_temporary_settings`, без `monkeypatch` (zero-mock canon).
    """
    from apps.sync.main import app

    async with _temporary_settings({"s3.enabled": False}):
        files = {"file": ("x.txt", io.BytesIO(b"data"), "text/plain")}
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.post(
                "/sync/api/v1/files/",
                headers=sync_auth_headers,
                files=files,
            )
    assert r.status_code == 503
    assert "S3" in r.json()["detail"]
