"""HTTP REST /worktracker/api/v1/files — upload roundtrip."""

from __future__ import annotations

import io

import pytest

from tests.worktracker.conftest import API_PREFIX
from tests.worktracker.helpers.assertions import assert_file_ref_json

pytestmark = pytest.mark.asyncio

FILES = f"{API_PREFIX}/files/"


async def test_upload_file_returns_file_response(worktracker_client) -> None:
    content = b"worktracker attachment payload"
    response = await worktracker_client.post(
        FILES,
        files={"file": ("attach.txt", io.BytesIO(content), "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert_file_ref_json(body)
    assert body["original_name"] == "attach.txt"
    assert body["content_type"] == "text/plain"
    assert body["file_size"] == len(content)


async def test_uploaded_file_used_in_work_item_attachment(
    worktracker_client,
    unique_id: str,
) -> None:
    upload = await worktracker_client.post(
        FILES,
        files={"file": ("doc.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
    )
    assert upload.status_code == 200
    file_ref = upload.json()

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
