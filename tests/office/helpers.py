"""Helpers для Office-тестов после миграции upload на frontend Files API."""

from __future__ import annotations

import io

from httpx import AsyncClient

from core.files.create_spec import (
    FileCreateSpec,
    FilePostCreate,
    FileSourceKind,
    FileSourceRef,
)
from core.files.registry import default_retention_for_source


def office_document_upload_spec_json(*, namespace: str = "default") -> str:
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=namespace),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        post_create=FilePostCreate(is_public=False),
    )
    return spec.model_dump_json()


async def upload_office_file_bytes(
    frontend_client: AsyncClient,
    headers: dict[str, str],
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    namespace: str = "default",
) -> dict[str, object]:
    upload_response = await frontend_client.post(
        "/frontend/api/v1/files/",
        headers=headers,
        data={"spec": office_document_upload_spec_json(namespace=namespace)},
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    if upload_response.status_code != 200:
        raise AssertionError(
            f"Office file upload failed: {upload_response.status_code} {upload_response.text}"
        )
    payload = upload_response.json()
    if not isinstance(payload, dict):
        raise TypeError("upload response must be JSON object")
    return payload
