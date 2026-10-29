"""
Интеграционные тесты единого файлового API платформы.

Single-shot POST /files/ снят; upload — только chunked /{svc}/api/v1/files/uploads*.
Peer-сервисы монтируют тот же chunked router на своём prefix.

Требует: S3 (SeaweedFS), shared DB.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)
from tests.fixtures.s3 import require_s3_configured
from tests.office.helpers import OFFICE_FILES_API_PREFIX, office_document_upload_spec_json

_TEST_IMAGE_PATH = Path(__file__).parent.parent / "2026-01-11 11.43.21.jpg"


@pytest.mark.asyncio
async def test_frontend_upload_returns_file_response(frontend_client, auth_headers_system):
    require_s3_configured()
    r = await chunked_upload_file(
        frontend_client,
        auth_headers_system,
        content=b"hello platform",
        original_name="readme.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "file_id" in data
    assert data["original_name"] == "readme.txt"
    assert data["content_type"] == "text/plain"
    assert data["file_size"] == 14
    assert data["is_public"] is True
    assert data["url"].startswith("/frontend/api/v1/files/download/")


@pytest.mark.asyncio
async def test_frontend_upload_real_jpeg(frontend_client, auth_headers_system):
    require_s3_configured()
    assert _TEST_IMAGE_PATH.is_file()
    image_data = _TEST_IMAGE_PATH.read_bytes()
    r = await chunked_upload_file(
        frontend_client,
        auth_headers_system,
        content=image_data,
        original_name=_TEST_IMAGE_PATH.name,
        content_type="image/jpeg",
        spec_json=platform_auxiliary_upload_spec_json(),
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["content_type"] == "image/jpeg"
    assert data["file_size"] == len(image_data)


@pytest.mark.asyncio
async def test_frontend_download_round_trip(frontend_client, auth_headers_system):
    require_s3_configured()
    content = b"round-trip content check"
    upload = await chunked_upload_file(
        frontend_client,
        auth_headers_system,
        content=content,
        original_name="roundtrip.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(),
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]
    download = await frontend_client.get(
        f"/frontend/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert download.status_code == 200
    assert download.content == content


@pytest.mark.asyncio
async def test_frontend_get_metadata(frontend_client, auth_headers_system):
    require_s3_configured()
    upload = await chunked_upload_file(
        frontend_client,
        auth_headers_system,
        content=b"meta",
        original_name="meta.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]
    meta = await frontend_client.get(
        f"/frontend/api/v1/files/{file_id}",
        headers=auth_headers_system,
    )
    assert meta.status_code == 200
    assert meta.json()["file_id"] == file_id


@pytest.mark.asyncio
async def test_frontend_upload_empty_file_rejected(frontend_client, auth_headers_system):
    require_s3_configured()
    with pytest.raises(ValueError, match="empty content"):
        await chunked_upload_file(
            frontend_client,
            auth_headers_system,
            content=b"",
            original_name="empty.txt",
            content_type="text/plain",
            spec_json=platform_auxiliary_upload_spec_json(),
        )


@pytest.mark.asyncio
async def test_upload_without_s3_returns_503(auth_headers_system, monkeypatch, frontend_app):
    monkeypatch.setenv("S3__ENABLED", "false")
    import core.config.base as config_base

    config_base._settings_instance = None
    from httpx2 import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=frontend_app), base_url="http://testserver") as client:
        r = await client.post(
            "/frontend/api/v1/files/uploads",
            headers={**auth_headers_system, "Content-Type": "application/json"},
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
    config_base._settings_instance = None


def _peer_files_upload_path(service: str) -> str:
    return f"/{service}/api/v1/files/"


def _peer_files_api_prefix(service: str) -> str:
    return f"/{service}/api/v1/files"


def _assert_single_shot_files_upload_rejected(response, service_name: str) -> None:
    assert response.status_code in (404, 405), (
        f"{service_name} must not expose single-shot POST /files/: "
        f"{response.status_code} {response.text}"
    )


async def _assert_peer_chunked_upload(client, headers: dict[str, str], service: str) -> None:
    require_s3_configured()
    content = b"peer chunked upload"
    prefix = _peer_files_api_prefix(service)
    response = await chunked_upload_file(
        client,
        headers,
        content=content,
        original_name="peer.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
        files_api_prefix=prefix,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["original_name"] == "peer.txt"
    assert payload["file_size"] == len(content)
    assert payload["file_id"]
    assert payload["url"].startswith(f"/{service}/api/v1/files/download/")
    download = await client.get(
        f"{prefix}/download/{payload['file_id']}",
        headers=headers,
    )
    assert download.status_code == 200
    assert download.content == content


@pytest.mark.asyncio
async def test_peer_upload_downloadable_on_other_service(
    crm_client,
    sync_client,
    auth_headers_system,
) -> None:
    require_s3_configured()
    content = b"cross-service download bytes"
    upload = await chunked_upload_file(
        crm_client,
        auth_headers_system,
        content=content,
        original_name="cross.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(is_public=False),
        files_api_prefix=_peer_files_api_prefix("crm"),
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]
    assert upload.json()["url"].startswith("/crm/api/v1/files/download/")

    download = await sync_client.get(
        f"/sync/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert download.status_code == 200
    assert download.content == content


@pytest.mark.asyncio
async def test_sync_rejects_single_shot_files_upload(sync_client, auth_headers_system) -> None:
    response = await sync_client.post(
        _peer_files_upload_path("sync"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_single_shot_files_upload_rejected(response, "sync")


@pytest.mark.asyncio
async def test_sync_chunked_files_upload(sync_client, auth_headers_system) -> None:
    await _assert_peer_chunked_upload(sync_client, auth_headers_system, "sync")


@pytest.mark.asyncio
async def test_crm_rejects_single_shot_files_upload(crm_client, auth_headers_system) -> None:
    response = await crm_client.post(
        _peer_files_upload_path("crm"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_single_shot_files_upload_rejected(response, "crm")


@pytest.mark.asyncio
async def test_crm_chunked_files_upload(crm_client, auth_headers_system) -> None:
    await _assert_peer_chunked_upload(crm_client, auth_headers_system, "crm")


@pytest.mark.asyncio
async def test_flows_rejects_single_shot_files_upload(flows_client, auth_headers_system) -> None:
    response = await flows_client.post(
        _peer_files_upload_path("flows"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_single_shot_files_upload_rejected(response, "flows")


@pytest.mark.asyncio
async def test_flows_chunked_files_upload(flows_client, auth_headers_system) -> None:
    await _assert_peer_chunked_upload(flows_client, auth_headers_system, "flows")


@pytest.mark.asyncio
async def test_rag_rejects_single_shot_files_upload(rag_client, auth_headers_system) -> None:
    response = await rag_client.post(
        _peer_files_upload_path("rag"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_single_shot_files_upload_rejected(response, "rag")


@pytest.mark.asyncio
async def test_rag_chunked_files_upload(rag_client, auth_headers_system) -> None:
    await _assert_peer_chunked_upload(rag_client, auth_headers_system, "rag")


@pytest.mark.asyncio
async def test_office_rejects_single_shot_files_upload(office_client, auth_headers_system) -> None:
    response = await office_client.post(
        _peer_files_upload_path("documents"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_single_shot_files_upload_rejected(response, "documents")


@pytest.mark.asyncio
async def test_office_chunked_files_upload(office_client, auth_headers_system) -> None:
    require_s3_configured()
    response = await chunked_upload_file(
        office_client,
        auth_headers_system,
        content=b"office chunked upload",
        original_name="office.txt",
        content_type="text/plain",
        spec_json=office_document_upload_spec_json(),
        files_api_prefix=OFFICE_FILES_API_PREFIX,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["original_name"] == "office.txt"
    assert payload["file_id"]
    assert payload["url"].startswith("/documents/api/v1/files/download/")
