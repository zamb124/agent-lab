"""Helpers для Office-тестов: chunked Files API на office + bind document."""

from __future__ import annotations

from httpx import AsyncClient

from core.documents.placement import DocumentPlacement
from core.files.create_spec import (
    FileCreateSpec,
    FilePostCreate,
    FileSourceKind,
    FileSourceRef,
)
from core.files.registry import default_retention_for_source
from tests.files.chunked_upload_helpers import chunked_upload_file

OFFICE_FILES_API_PREFIX = "/documents/api/v1/files"


def office_document_upload_spec_json(*, namespace: str = "default") -> str:
    spec = FileCreateSpec(
        source_kind=FileSourceKind.OFFICE_DOCUMENT,
        source_ref=FileSourceRef(entity_id=namespace),
        retention=default_retention_for_source(FileSourceKind.OFFICE_DOCUMENT),
        placement=DocumentPlacement(catalog_path=["Documents"]),
        post_create=FilePostCreate(is_public=False),
    )
    return spec.model_dump_json()


async def upload_office_file_bytes(
    office_client: AsyncClient,
    headers: dict[str, str],
    *,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
    namespace: str = "default",
) -> dict[str, object]:
    upload_response = await chunked_upload_file(
        office_client,
        headers,
        content=content,
        original_name=filename,
        content_type=content_type,
        spec_json=office_document_upload_spec_json(namespace=namespace),
        files_api_prefix=OFFICE_FILES_API_PREFIX,
    )
    if upload_response.status_code != 200:
        raise AssertionError(
            f"Office file upload failed: {upload_response.status_code} {upload_response.text}"
        )
    payload = upload_response.json()
    if not isinstance(payload, dict):
        raise TypeError("upload response must be JSON object")
    return payload
