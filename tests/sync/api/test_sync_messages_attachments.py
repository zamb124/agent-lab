"""Сообщения с вложениями file/image и file/document: загрузка в S3, TaskIQ, лента."""

from __future__ import annotations

import pytest

from tests.sync.api._helpers import create_topic_channel_via_http, upload_platform_file


async def _create_topic_channel(
    sync_client, sync_auth_headers, company_id: str, unique_id: str
) -> str:
    return await create_topic_channel_via_http(
        sync_client,
        sync_auth_headers,
        company_id=company_id,
        unique_id=unique_id,
        suffix="attach",
        channel_name="attach_chan",
    )


@pytest.mark.asyncio
async def test_http_send_message_file_document_list_round_trip(
    sync_client,
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers, company_id, unique_id)

    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    up = await upload_platform_file(
        frontend_client,
        sync_auth_headers,
        filename="report.pdf",
        content=pdf_bytes,
        content_type="application/pdf",
    )
    assert up.status_code == 200, up.text
    f = up.json()
    file_id = f["file_id"]

    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {
                    "type": "file/document",
                    "order": 0,
                    "data": {
                        "file_id": file_id,
                        "original_name": "report.pdf",
                        "content_type": "application/pdf",
                        "file_size": f["file_size"],
                    },
                },
            ],
        },
    )
    assert sr.status_code == 201, sr.text

    lr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert lr.status_code == 200
    msgs = lr.json()["items"]
    assert len(msgs) == 1
    assert len(msgs[0]["contents"]) == 1
    c0 = msgs[0]["contents"][0]
    assert c0["type"] == "file/document"
    assert c0["order"] == 0
    assert c0["data"]["file_id"] == file_id
    assert c0["data"]["original_name"] == "report.pdf"
    assert c0["data"]["content_type"] == "application/pdf"
    assert c0["data"]["file_size"] == f["file_size"]


@pytest.mark.asyncio
async def test_http_send_message_file_image_with_text_plain(
    sync_client,
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers, company_id, unique_id)

    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00"
        b"\xff\xd9"
    )
    up = await upload_platform_file(
        frontend_client,
        sync_auth_headers,
        filename="photo.jpg",
        content=jpeg_bytes,
        content_type="image/jpeg",
    )
    assert up.status_code == 200, up.text
    f = up.json()
    file_id = f["file_id"]

    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {
                    "type": "text/plain",
                    "order": 0,
                    "data": {"body": "смотри фото"},
                },
                {
                    "type": "file/image",
                    "order": 1,
                    "data": {
                        "file_id": file_id,
                        "original_name": "photo.jpg",
                        "content_type": "image/jpeg",
                        "file_size": f["file_size"],
                    },
                },
            ],
        },
    )
    assert sr.status_code == 201, sr.text

    lr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert lr.status_code == 200
    msgs = lr.json()["items"]
    assert len(msgs) == 1
    contents = msgs[0]["contents"]
    assert len(contents) == 2
    assert contents[0]["type"] == "text/plain"
    assert contents[0]["data"]["body"] == "смотри фото"
    assert contents[1]["type"] == "file/image"
    assert contents[1]["data"]["file_id"] == file_id
    assert contents[1]["data"]["original_name"] == "photo.jpg"
    assert contents[1]["data"]["content_type"] == "image/jpeg"
    assert contents[1]["data"]["file_size"] == f["file_size"]


@pytest.mark.asyncio
async def test_http_send_message_two_file_attachments_one_message(
    sync_client,
    frontend_client,
    sync_auth_headers,
    sync_db_clean: None,
    company_id: str,
    unique_id: str,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers, company_id, unique_id)

    up1 = await upload_platform_file(
        frontend_client,
        sync_auth_headers,
        filename="a.txt",
        content=b"alpha",
        content_type="text/plain",
    )
    assert up1.status_code == 200, up1.text
    fa = up1.json()

    up2 = await upload_platform_file(
        frontend_client,
        sync_auth_headers,
        filename="b.txt",
        content=b"beta-longer",
        content_type="text/plain",
    )
    assert up2.status_code == 200, up2.text
    fb = up2.json()

    sr = await sync_client.post(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
        json={
            "thread_id": None,
            "parent_message_id": None,
            "contents": [
                {
                    "type": "file/document",
                    "order": 0,
                    "data": {
                        "file_id": fa["file_id"],
                        "original_name": "a.txt",
                        "content_type": "text/plain",
                        "file_size": fa["file_size"],
                    },
                },
                {
                    "type": "file/document",
                    "order": 1,
                    "data": {
                        "file_id": fb["file_id"],
                        "original_name": "b.txt",
                        "content_type": "text/plain",
                        "file_size": fb["file_size"],
                    },
                },
            ],
        },
    )
    assert sr.status_code == 201, sr.text

    lr = await sync_client.get(
        f"/sync/api/v1/channels/{channel_id}/messages",
        headers=sync_auth_headers,
    )
    assert lr.status_code == 200
    msgs = lr.json()["items"]
    assert len(msgs) == 1
    contents = msgs[0]["contents"]
    assert len(contents) == 2
    assert contents[0]["data"]["file_id"] == fa["file_id"]
    assert contents[1]["data"]["file_id"] == fb["file_id"]
