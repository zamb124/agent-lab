"""Сообщения с вложениями file/image и file/document: загрузка в S3, TaskIQ, лента."""

from __future__ import annotations

import io

import pytest


async def _create_topic_channel(sync_client, sync_auth_headers) -> str:
    pr = await sync_client.post(
        "/sync/api/v1/spaces/",
        headers=sync_auth_headers,
        json={"name": "AttachSpace", "description": None},
    )
    assert pr.status_code == 201
    space_id = pr.json()["id"]
    cr = await sync_client.post(
        "/sync/api/v1/channels/",
        headers=sync_auth_headers,
        json={
            "space_id": space_id,
            "type": "topic",
            "name": "attach_chan",
            "is_private": False,
        },
    )
    assert cr.status_code == 201
    return cr.json()["id"]


@pytest.mark.asyncio
async def test_http_send_message_file_document_list_round_trip(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers)

    pdf_bytes = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
    up = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("report.pdf", io.BytesIO(pdf_bytes), "application/pdf")},
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
                        "filename": "report.pdf",
                        "mime_type": "application/pdf",
                        "size": f["file_size"],
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
    assert c0["data"]["filename"] == "report.pdf"
    assert c0["data"]["mime_type"] == "application/pdf"
    assert c0["data"]["size"] == f["file_size"]


@pytest.mark.asyncio
async def test_http_send_message_file_image_with_text_plain(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers)

    jpeg_bytes = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xdb\x00C\x00"
        b"\xff\xd9"
    )
    up = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("photo.jpg", io.BytesIO(jpeg_bytes), "image/jpeg")},
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
                        "filename": "photo.jpg",
                        "mime_type": "image/jpeg",
                        "size": f["file_size"],
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
    assert contents[1]["data"]["filename"] == "photo.jpg"
    assert contents[1]["data"]["mime_type"] == "image/jpeg"
    assert contents[1]["data"]["size"] == f["file_size"]


@pytest.mark.asyncio
async def test_http_send_message_two_file_attachments_one_message(
    sync_client,
    sync_auth_headers,
    sync_db_clean: None,
) -> None:
    channel_id = await _create_topic_channel(sync_client, sync_auth_headers)

    up1 = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("a.txt", io.BytesIO(b"alpha"), "text/plain")},
    )
    assert up1.status_code == 200, up1.text
    fa = up1.json()

    up2 = await sync_client.post(
        "/sync/api/v1/files/",
        headers=sync_auth_headers,
        files={"file": ("b.txt", io.BytesIO(b"beta-longer"), "text/plain")},
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
                        "filename": "a.txt",
                        "mime_type": "text/plain",
                        "size": fa["file_size"],
                    },
                },
                {
                    "type": "file/document",
                    "order": 1,
                    "data": {
                        "file_id": fb["file_id"],
                        "filename": "b.txt",
                        "mime_type": "text/plain",
                        "size": fb["file_size"],
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
