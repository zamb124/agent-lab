"""POST /frontend/api/v1/files/ — реальный S3 (MinIO), ASGI + worker не обязателен."""

from __future__ import annotations

import io
import json

import pytest


def _platform_auxiliary_spec() -> str:
    return json.dumps(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": True},
        }
    )


@pytest.mark.asyncio
async def test_upload_file_multipart(
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    files = {"file": ("hello.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=sync_auth_headers,
        data={"spec": _platform_auxiliary_spec()},
        files=files,
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
