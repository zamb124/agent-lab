"""Chunked Files API: init, parts, complete."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path

from platform_sdk.errors import parse
from platform_sdk.http import PlatformClient
from platform_sdk.json_types import JsonObject
from platform_sdk.wire import FileRef, UploadConfig, UploadInit, dump


async def upload_file(
    client: PlatformClient,
    path: Path,
    *,
    segment: str,
    spec: JsonObject,
) -> JsonObject:
    data = path.read_bytes()
    if len(data) == 0:
        raise ValueError(f"{path} is empty")
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type is None:
        content_type = "application/octet-stream"
    prefix = f"/{segment}/api/v1/files"
    config = parse(
        UploadConfig,
        await client.request("GET", f"{prefix}/upload-config", retry=True),
        "upload-config",
    )
    digest = hashlib.sha256(data).hexdigest()
    initiated = parse(
        UploadInit,
        await client.request(
            "POST",
            f"{prefix}/uploads",
            json_body={
                "spec": spec,
                "original_name": path.name,
                "content_type": content_type,
                "file_size": len(data),
                "content_sha256_hex": digest,
            },
        ),
        "upload-init",
    )
    upload_id = initiated.upload_id
    chunk_size = config.chunk_size_bytes
    part = 1
    offset = 0
    while offset < len(data):
        piece = data[offset : offset + chunk_size]
        await client.request(
            "PUT",
            f"{prefix}/uploads/{upload_id}/parts/{part}",
            content=piece,
            headers={"Content-Type": "application/octet-stream"},
        )
        offset += len(piece)
        part += 1
    completed = parse(
        FileRef,
        await client.request("POST", f"{prefix}/uploads/{upload_id}/complete"),
        "upload-complete",
    )
    return dump(completed)
