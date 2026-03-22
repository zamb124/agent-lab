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
    from core.config import get_settings

    settings = get_settings()
    if not settings.s3.enabled or not settings.s3.default_bucket:
        raise RuntimeError(
            "Для теста загрузки нужны S3__ENABLED=true и bucket (MinIO на 19002 по конфигу)."
        )

    files = {"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = await sync_client.post(
        "/sync/api/v1/files/",
        headers=auth_headers_system,
        files=files,
    )
    assert r.status_code == 200
    data = r.json()
    assert "file" in data
    assert data["file"]["original_name"] == "hello.txt"
    assert data["file"]["size_bytes"] == 11

    file_id = data["file"]["id"]
    gr = await sync_client.get(f"/sync/api/v1/files/{file_id}", headers=auth_headers_system)
    assert gr.status_code == 200
    assert gr.json()["id"] == file_id
