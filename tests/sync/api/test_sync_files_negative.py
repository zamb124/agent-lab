"""Негативные сценарии Files API."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
)
from tests.sync.api._helpers import platform_auxiliary_file_spec_json
from tests.sync.integration.conftest import _temporary_settings


@pytest.mark.asyncio
async def test_upload_empty_file_400(
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    with pytest.raises(ValueError, match="empty content"):
        await chunked_upload_file(
            frontend_client,
            sync_auth_headers,
            content=b"",
            original_name="empty.txt",
            content_type="text/plain",
            spec_json=platform_auxiliary_file_spec_json(),
        )


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
    frontend_app,
) -> None:
    async with _temporary_settings({"s3.enabled": False}):
        transport = ASGITransport(app=frontend_app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            r = await client.post(
                "/frontend/api/v1/files/uploads",
                headers={**sync_auth_headers, "Content-Type": "application/json"},
                json={
                    "spec": {
                        "source_kind": "platform_auxiliary",
                        "source_ref": {},
                        "retention": {"kind": "platform_default"},
                        "post_create": {"is_public": True},
                    },
                    "original_name": "x.txt",
                    "content_type": "text/plain",
                    "file_size": 4,
                },
            )
    assert r.status_code == 503
    assert "S3" in r.json()["detail"]
