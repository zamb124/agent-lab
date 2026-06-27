"""
HTTP bind и негативные сценарии unified Files API.
"""

from __future__ import annotations

import io
import json

import pytest

from tests.fixtures.s3 import require_s3_configured
from tests.sync.api._helpers import platform_auxiliary_file_spec_json, upload_platform_file


@pytest.mark.asyncio
async def test_bind_rejects_mismatched_file_id(frontend_client, auth_headers_system, unique_id: str):
    require_s3_configured()
    upload = await upload_platform_file(
        frontend_client,
        auth_headers_system,
        filename=f"bind-{unique_id}.txt",
        content=f"bind-{unique_id}".encode("utf-8"),
        content_type="text/plain",
        is_public=False,
    )
    assert upload.status_code == 200, upload.text
    file_id = upload.json()["file_id"]

    placement = {
        "namespace": "default",
        "file_id": "ffffffffffffffffffffffffffffffff",
        "title": f"bind-{unique_id}",
    }
    response = await frontend_client.post(
        f"/frontend/api/v1/files/{file_id}/bind",
        headers=auth_headers_system,
        json=placement,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_download_missing_file_404(frontend_client, auth_headers_system):
    response = await frontend_client.get(
        "/frontend/api/v1/files/download/ffffffffffffffffffffffffffffffff",
        headers=auth_headers_system,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_metadata_missing_file_404(frontend_client, auth_headers_system):
    response = await frontend_client.get(
        "/frontend/api/v1/files/ffffffffffffffffffffffffffffffff",
        headers=auth_headers_system,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_missing_spec_422(frontend_client, auth_headers_system):
    response = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_files_service_bind_file_id_mismatch_raises(app):
    _ = app
    from apps.frontend.container import get_frontend_container
    from core.documents.placement import DocsPlacement

    container = get_frontend_container()
    placement = DocsPlacement.model_validate(
        {
            "namespace": "default",
            "file_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "title": "x",
        }
    )
    with pytest.raises(ValueError, match="file_id"):
        await container.files_service.bind("bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", placement)


def test_platform_auxiliary_spec_json_valid():
    parsed = json.loads(platform_auxiliary_file_spec_json(is_public=False))
    assert parsed["source_kind"] == "platform_auxiliary"
    assert parsed["retention"]["kind"] == "platform_default"
    assert parsed["post_create"]["is_public"] is False
