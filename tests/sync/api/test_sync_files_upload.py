"""Chunked upload /frontend/api/v1/files/uploads — реальный S3 (MinIO)."""

from __future__ import annotations

import pytest

from tests.files.chunked_upload_helpers import chunked_upload_file, platform_auxiliary_upload_spec_json


@pytest.mark.asyncio
async def test_upload_file_chunked(
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    r = await chunked_upload_file(
        frontend_client,
        sync_auth_headers,
        content=b"hello world",
        original_name="hello.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=True),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["original_name"] == "hello.txt"
    assert data["file_size"] == 11
    assert "/frontend/api/v1/files/download/" in data["url"]

    file_id = data["file_id"]
    gr = await frontend_client.get(f"/frontend/api/v1/files/{file_id}", headers=sync_auth_headers)
    assert gr.status_code == 200
    assert gr.json()["file_id"] == file_id
