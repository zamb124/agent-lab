"""
FilesClient — HTTP-обёртка над frontend /frontend/api/v1/files/*.
"""

from __future__ import annotations

import pytest

from core.clients.files_client import FilesClient
from core.files.create_spec import FileCreateSpec
from tests.fixtures.auth import service_client_asgi_auth_context


def _platform_auxiliary_spec() -> FileCreateSpec:
    return FileCreateSpec.model_validate(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
        }
    )


@pytest.mark.asyncio
async def test_files_client_create_via_frontend(frontend_client, auth_headers_system, unique_id: str):
    from core.files.s3_client import S3ClientFactory

    S3ClientFactory.create_default_client()
    payload = f"client-{unique_id}".encode("utf-8")

    client = FilesClient()
    with service_client_asgi_auth_context(auth_headers_system):
        response = await client.create(
            _platform_auxiliary_spec(),
            payload,
            original_name=f"client-{unique_id}.txt",
            content_type="text/plain",
        )
    assert response.file_id
    assert response.url.startswith("/frontend/api/v1/files/download/")

    download = await frontend_client.get(
        f"/frontend/api/v1/files/download/{response.file_id}",
        headers=auth_headers_system,
    )
    assert download.status_code == 200
    assert download.content == payload


@pytest.mark.asyncio
async def test_files_client_register_s3(frontend_client, auth_headers_system, unique_id: str):
    from core.config import get_settings
    from core.files.s3_client import S3ClientFactory

    S3ClientFactory.create_default_client()
    settings = get_settings()
    bucket = settings.s3.default_bucket
    if bucket is None or bucket == "":
        pytest.fail("S3 default_bucket is required")

    s3_key = f"test/files-client/{unique_id}.bin"
    payload = b"files client register"
    s3_client = S3ClientFactory.create_default_client()
    _ = await s3_client.upload_bytes(payload, s3_key, content_type="application/octet-stream")

    client = FilesClient()
    with service_client_asgi_auth_context(auth_headers_system):
        response = await client.register_s3(
            _platform_auxiliary_spec(),
            s3_key=s3_key,
            s3_bucket=bucket,
            original_name=f"{unique_id}.bin",
            content_type="application/octet-stream",
            file_size=len(payload),
        )
    assert response.file_id
    meta = await frontend_client.get(
        f"/frontend/api/v1/files/{response.file_id}",
        headers=auth_headers_system,
    )
    assert meta.status_code == 200
    assert meta.json()["file_size"] == len(payload)
