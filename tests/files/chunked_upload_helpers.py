"""Единый HTTP-хелпер chunked upload для тестов (реальный MinIO + Files API)."""

from __future__ import annotations

from typing import Mapping

from httpx import AsyncClient, Response

from core.files.create_spec import FileCreateSpec, FilePostCreate, FileSourceKind, FileSourceRef
from core.files.registry import default_retention_for_source
from core.types import require_json_object

DEFAULT_FILES_API_PREFIX = "/frontend/api/v1/files"


def platform_auxiliary_upload_spec_json(*, is_public: bool = True) -> str:
    spec = FileCreateSpec(
        source_kind=FileSourceKind.PLATFORM_AUXILIARY,
        source_ref=FileSourceRef(),
        retention=default_retention_for_source(FileSourceKind.PLATFORM_AUXILIARY),
        post_create=FilePostCreate(is_public=is_public),
    )
    return spec.model_dump_json()


def flow_asset_upload_spec_json(*, flow_id: str, is_public: bool) -> str:
    if flow_id.strip() == "":
        raise ValueError("flow_asset_upload_spec_json: flow_id required")
    spec = FileCreateSpec(
        source_kind=FileSourceKind.FLOW_ASSET,
        source_ref=FileSourceRef(flow_id=flow_id),
        retention=default_retention_for_source(FileSourceKind.FLOW_ASSET),
        post_create=FilePostCreate(is_public=is_public),
    )
    return spec.model_dump_json()


async def chunked_upload_file(
    client: AsyncClient,
    headers: Mapping[str, str],
    *,
    content: bytes,
    original_name: str,
    content_type: str,
    spec_json: str,
    files_api_prefix: str = DEFAULT_FILES_API_PREFIX,
) -> Response:
    """init → PUT parts → complete. Возвращает Response complete (FileResponse JSON)."""
    if len(content) == 0:
        raise ValueError("chunked_upload_file: empty content")
    if original_name.strip() == "":
        raise ValueError("chunked_upload_file: original_name required")
    if content_type.strip() == "":
        raise ValueError("chunked_upload_file: content_type required")
    if spec_json.strip() == "":
        raise ValueError("chunked_upload_file: spec_json required")
    prefix = files_api_prefix.rstrip("/")
    if prefix == "":
        raise ValueError("chunked_upload_file: files_api_prefix required")

    init_response = await client.post(
        f"{prefix}/uploads",
        headers=headers,
        json={
            "spec": FileCreateSpec.model_validate_json(spec_json).model_dump(mode="json"),
            "original_name": original_name,
            "content_type": content_type,
            "file_size": len(content),
        },
    )
    if init_response.status_code != 200:
        return init_response
    init_body = require_json_object(init_response.json(), "chunked init")
    upload_id = init_body.get("upload_id")
    if not isinstance(upload_id, str) or upload_id == "":
        raise AssertionError("chunked init: upload_id required")
    chunk_size_raw = init_body.get("chunk_size_bytes")
    if not isinstance(chunk_size_raw, int) or chunk_size_raw < 1:
        raise AssertionError("chunked init: chunk_size_bytes required")

    offset = 0
    part_number = 1
    while offset < len(content):
        end = min(offset + chunk_size_raw, len(content))
        part = content[offset:end]
        put_response = await client.put(
            f"{prefix}/uploads/{upload_id}/parts/{part_number}",
            headers=headers,
            content=part,
        )
        if put_response.status_code != 200:
            return put_response
        offset = end
        part_number += 1

    return await client.post(
        f"{prefix}/uploads/{upload_id}/complete",
        headers=headers,
    )


__all__ = [
    "DEFAULT_FILES_API_PREFIX",
    "chunked_upload_file",
    "flow_asset_upload_spec_json",
    "platform_auxiliary_upload_spec_json",
]
