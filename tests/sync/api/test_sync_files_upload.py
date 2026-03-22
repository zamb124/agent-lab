"""POST /sync/api/v1/files/ — реальный S3 (MinIO), ASGI + worker не обязателен."""

from __future__ import annotations

import io

import pytest


@pytest.mark.asyncio
async def test_upload_file_multipart(
    sync_client,
    auth_headers_system,
    sync_db_clean: None,
) -> None:
    files = {"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files=files,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["original_name"] == "hello.txt"
    assert data["file_size"] == 11
    assert "/sync/api/v1/files/download/" in data["url"]

    file_id = data["file_id"]
    gr = await sync_client.get(f"/sync/api/v1/files/{file_id}", headers=auth_headers_system)
    assert gr.status_code == 200
    assert gr.json()["file_id"] == file_id
