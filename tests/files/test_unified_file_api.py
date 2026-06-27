"""
Интеграционные тесты единого файлового API платформы.

HTTP upload/download — только /frontend/api/v1/files/*.
Peer-сервисы не монтируют POST upload на своём /api/v1/files/.

Требует: MinIO (S3), shared DB.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from tests.fixtures.s3 import require_s3_configured

_TEST_IMAGE_PATH = Path(__file__).parent.parent / "2026-01-11 11.43.21.jpg"


def _platform_auxiliary_spec(*, is_public: bool = True) -> str:
    return json.dumps(
        {
            "source_kind": "platform_auxiliary",
            "source_ref": {},
            "retention": {"kind": "platform_default"},
            "post_create": {"is_public": is_public},
        }
    )


@pytest.mark.asyncio
async def test_frontend_upload_returns_file_response(frontend_client, auth_headers_system):
    require_s3_configured()
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": _platform_auxiliary_spec()},
        files={"file": ("readme.txt", io.BytesIO(b"hello platform"), "text/plain")},
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
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": _platform_auxiliary_spec()},
        files={"file": (_TEST_IMAGE_PATH.name, io.BytesIO(image_data), "image/jpeg")},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["content_type"] == "image/jpeg"
    assert data["file_size"] == len(image_data)


@pytest.mark.asyncio
async def test_frontend_download_round_trip(frontend_client, auth_headers_system):
    require_s3_configured()
    content = b"round-trip content check"
    upload = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": _platform_auxiliary_spec()},
        files={"file": ("roundtrip.txt", io.BytesIO(content), "text/plain")},
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
    upload = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": _platform_auxiliary_spec(is_public=False)},
        files={"file": ("meta.txt", io.BytesIO(b"meta"), "text/plain")},
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
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": _platform_auxiliary_spec()},
        files={"file": ("empty.txt", io.BytesIO(b""), "text/plain")},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_upload_without_s3_returns_503(auth_headers_system, monkeypatch):
    monkeypatch.setenv("S3__ENABLED", "false")
    import core.config.base as config_base

    config_base._settings_instance = None
    from httpx import ASGITransport, AsyncClient

    from apps.frontend.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        r = await client.post(
            "/frontend/api/v1/files/",
            headers=auth_headers_system,
            data={"spec": _platform_auxiliary_spec()},
            files={"file": ("x.txt", io.BytesIO(b"data"), "text/plain")},
        )
    assert r.status_code == 503
    config_base._settings_instance = None


def _peer_files_upload_path(service: str) -> str:
    return f"/{service}/api/v1/files/"


def _assert_peer_has_no_files_upload(response, service_name: str) -> None:
    assert response.status_code in (404, 405), (
        f"{service_name} must not expose POST /files/: {response.status_code} {response.text}"
    )


@pytest.mark.asyncio
async def test_sync_has_no_files_upload(sync_client, auth_headers_system):
    r = await sync_client.post(
        _peer_files_upload_path("sync"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_peer_has_no_files_upload(r, "sync")


@pytest.mark.asyncio
async def test_crm_has_no_files_upload(crm_client, auth_headers_system):
    r = await crm_client.post(
        _peer_files_upload_path("crm"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_peer_has_no_files_upload(r, "crm")


@pytest.mark.asyncio
async def test_rag_has_no_files_upload(rag_client, auth_headers_system):
    r = await rag_client.post(
        _peer_files_upload_path("rag"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_peer_has_no_files_upload(r, "rag")


@pytest.mark.asyncio
async def test_flows_has_no_files_upload(flows_client, auth_headers_system):
    r = await flows_client.post(
        _peer_files_upload_path("flows"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_peer_has_no_files_upload(r, "flows")


@pytest.mark.asyncio
async def test_worktracker_has_no_files_upload(worktracker_client, auth_headers_system):
    r = await worktracker_client.post(
        _peer_files_upload_path("worktracker"),
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    _assert_peer_has_no_files_upload(r, "worktracker")
