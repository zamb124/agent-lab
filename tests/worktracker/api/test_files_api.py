"""Файлы worktracker — upload только через /frontend/api/v1/files/."""

from __future__ import annotations

import io

import pytest

from tests.sync.api._helpers import upload_platform_file
from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.assertions import assert_file_ref_json

pytestmark = pytest.mark.asyncio


async def test_worktracker_has_no_files_upload_route(worktracker_client) -> None:
    response = await worktracker_client.post(
        f"{API_PREFIX}/files/",
        files={"file": ("attach.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert response.status_code in (404, 405)


async def test_upload_via_frontend_used_in_work_item_attachment(
    frontend_client,
    worktracker_client,
    auth_headers_system,
    unique_id: str,
) -> None:
    content = b"worktracker attachment payload"
    upload = await upload_platform_file(
        frontend_client,
        auth_headers_system,
        filename="attach.txt",
        content=content,
        content_type="text/plain",
        is_public=False,
    )
    assert upload.status_code == 200, upload.text
    file_ref = upload.json()
    assert_file_ref_json(file_ref)
    assert file_ref["original_name"] == "attach.txt"
    assert file_ref["content_type"] == "text/plain"
    assert file_ref["file_size"] == len(content)
    assert file_ref["url"].startswith("/frontend/api/v1/files/download/")

    create = await worktracker_client.post(
        f"{API_PREFIX}/work-items",
        json={
            "title": f"With file {unique_id}",
            "attachments": [
                {
                    "file_id": file_ref["file_id"],
                    "original_name": file_ref["original_name"],
                    "content_type": file_ref["content_type"],
                    "file_size": file_ref["file_size"],
                    "url": file_ref["url"],
                }
            ],
        },
    )
    assert create.status_code == 201
    attachments = create.json()["attachments"]
    assert len(attachments) == 1
    assert attachments[0]["file_id"] == file_ref["file_id"]
