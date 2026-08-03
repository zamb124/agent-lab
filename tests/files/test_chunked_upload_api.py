"""Chunked upload API: init → parts → complete / abort."""

from __future__ import annotations

import hashlib
import io
import json

import pytest

from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    platform_auxiliary_upload_spec_json,
)
from tests.fixtures.s3 import require_s3_configured


def _platform_auxiliary_spec(*, is_public: bool = True) -> dict[str, object]:
    return {
        "source_kind": "platform_auxiliary",
        "source_ref": {},
        "retention": {"kind": "platform_default"},
        "post_create": {"is_public": is_public},
    }


@pytest.mark.asyncio
async def test_chunked_upload_round_trip(frontend_client, auth_headers_system):
    require_s3_configured()
    chunk_size = 5 * 1024 * 1024
    # two full parts + remainder
    payload = (b"A" * chunk_size) + (b"B" * chunk_size) + (b"C" * 1234)
    checksum = hashlib.sha256(payload).hexdigest()

    init = await frontend_client.post(
        "/frontend/api/v1/files/uploads",
        headers={**auth_headers_system, "Content-Type": "application/json"},
        json={
            "spec": _platform_auxiliary_spec(),
            "original_name": "big.bin",
            "content_type": "application/octet-stream",
            "file_size": len(payload),
            "content_sha256_hex": checksum,
        },
    )
    assert init.status_code == 200, init.text
    init_body = init.json()
    upload_id = init_body["upload_id"]
    file_id = init_body["file_id"]
    assert init_body["chunk_size_bytes"] == chunk_size

    offset = 0
    part_number = 1
    while offset < len(payload):
        end = min(offset + chunk_size, len(payload))
        part_bytes = payload[offset:end]
        put = await frontend_client.put(
            f"/frontend/api/v1/files/uploads/{upload_id}/parts/{part_number}",
            headers={
                **auth_headers_system,
                "Content-Type": "application/octet-stream",
                "Content-Length": str(len(part_bytes)),
            },
            content=part_bytes,
        )
        assert put.status_code == 200, put.text
        part = put.json()
        assert part["part_number"] == part_number
        assert part["size"] == len(part_bytes)
        offset = end
        part_number += 1

    complete = await frontend_client.post(
        f"/frontend/api/v1/files/uploads/{upload_id}/complete",
        headers=auth_headers_system,
    )
    assert complete.status_code == 200, complete.text
    meta = complete.json()
    assert meta["file_id"] == file_id
    assert meta["file_size"] == len(payload)
    assert meta["original_name"] == "big.bin"
    assert meta["checksum"] == checksum

    download = await frontend_client.get(
        f"/frontend/api/v1/files/download/{file_id}",
        headers=auth_headers_system,
    )
    assert download.status_code == 200
    assert download.content == payload


@pytest.mark.asyncio
async def test_chunked_upload_abort(frontend_client, auth_headers_system):
    require_s3_configured()
    init = await frontend_client.post(
        "/frontend/api/v1/files/uploads",
        headers={**auth_headers_system, "Content-Type": "application/json"},
        json={
            "spec": _platform_auxiliary_spec(),
            "original_name": "abort.bin",
            "content_type": "application/octet-stream",
            "file_size": 5 * 1024 * 1024 + 10,
        },
    )
    assert init.status_code == 200, init.text
    upload_id = init.json()["upload_id"]

    abort = await frontend_client.delete(
        f"/frontend/api/v1/files/uploads/{upload_id}",
        headers=auth_headers_system,
    )
    assert abort.status_code == 204

    complete = await frontend_client.post(
        f"/frontend/api/v1/files/uploads/{upload_id}/complete",
        headers=auth_headers_system,
    )
    assert complete.status_code == 400


@pytest.mark.asyncio
async def test_chunked_upload_rejects_out_of_order_part(frontend_client, auth_headers_system):
    require_s3_configured()
    chunk_size = 5 * 1024 * 1024
    init = await frontend_client.post(
        "/frontend/api/v1/files/uploads",
        headers={**auth_headers_system, "Content-Type": "application/json"},
        json={
            "spec": _platform_auxiliary_spec(),
            "original_name": "order.bin",
            "content_type": "application/octet-stream",
            "file_size": chunk_size * 2,
        },
    )
    assert init.status_code == 200, init.text
    upload_id = init.json()["upload_id"]
    bad = await frontend_client.put(
        f"/frontend/api/v1/files/uploads/{upload_id}/parts/2",
        headers={
            **auth_headers_system,
            "Content-Type": "application/octet-stream",
            "Content-Length": str(chunk_size),
        },
        content=b"X" * chunk_size,
    )
    assert bad.status_code == 400


@pytest.mark.asyncio
async def test_single_shot_post_removed(frontend_client, auth_headers_system):
    require_s3_configured()
    r = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=auth_headers_system,
        data={"spec": json.dumps(_platform_auxiliary_spec())},
        files={"file": ("small.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert r.status_code in (404, 405, 422)

    ok = await chunked_upload_file(
        frontend_client,
        auth_headers_system,
        content=b"hello chunked only",
        original_name="small.txt",
        content_type="text/plain",
        spec_json=platform_auxiliary_upload_spec_json(),
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["file_size"] == 18


@pytest.mark.asyncio
async def test_upload_config_has_no_single_shot(frontend_client, auth_headers_system):
    r = await frontend_client.get(
        "/frontend/api/v1/files/upload-config",
        headers=auth_headers_system,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "single_shot_max_bytes" not in body
    assert body["chunk_size_bytes"] >= 5 * 1024 * 1024
    assert body["max_upload_bytes"] >= body["chunk_size_bytes"]
