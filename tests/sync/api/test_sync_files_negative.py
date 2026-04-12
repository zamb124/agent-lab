"""Негативные сценарии Files API."""

from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient


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
async def test_upload_returns_503_when_s3_disabled_via_env(
    monkeypatch: pytest.MonkeyPatch,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    monkeypatch.setenv("S3__ENABLED", "false")

    import core.config.base as config_base

    config_base._settings_instance = None

    from apps.sync.main import app

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

    config_base._settings_instance = None
