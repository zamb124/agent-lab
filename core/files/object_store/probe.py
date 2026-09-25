"""Проверка, что ключи реально читают и пишут бакет, до того как строка станет active."""

from __future__ import annotations

import uuid

from core.files.object_store.pool import build_client
from core.files.object_store.resolved import ResolvedStorage


async def probe_storage(resolved: ResolvedStorage) -> None:
    client = build_client(resolved)
    key = f".probe/{uuid.uuid4().hex}"
    payload = b"probe"
    try:
        _ = await client.upload_bytes(data=payload, key=key, content_type="application/octet-stream")
        downloaded = await client.download_bytes(key)
        if downloaded != payload:
            raise ValueError("storage probe read did not match the written object")
        _ = await client.delete_file(key)
        upload_id = await client.create_multipart_upload(key, content_type="application/octet-stream")
        await client.abort_multipart_upload(key, upload_id=upload_id)
    finally:
        await client.close()
