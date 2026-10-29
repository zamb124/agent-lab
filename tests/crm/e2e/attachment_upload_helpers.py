"""CRM e2e: chunked Files upload + attach by file_id."""

from __future__ import annotations

from typing import cast

from httpx2 import AsyncClient, Response

from core.files.create_spec import (
    FileCreateSpec,
    FilePostCreate,
    FileSourceKind,
    FileSourceRef,
)
from core.files.registry import default_retention_for_source
from core.types import require_json_object
from tests.crm.e2e._json_helpers import object_str
from tests.files.chunked_upload_helpers import chunked_upload_file

CRM_FILES_API_PREFIX = "/crm/api/v1/files"


def crm_entity_upload_spec_json(
    *,
    entity_id: str,
    entity_type: str,
    entity_title: str,
) -> str:
    spec = FileCreateSpec(
        source_kind=FileSourceKind.CRM_ENTITY,
        source_ref=FileSourceRef(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_title=entity_title,
        ),
        retention=default_retention_for_source(FileSourceKind.CRM_ENTITY),
        post_create=FilePostCreate(is_public=False),
    )
    return spec.model_dump_json()


async def upload_and_attach_crm_file(
    crm_client: AsyncClient,
    headers: dict[str, str],
    *,
    entity_id: str,
    entity_type: str,
    entity_title: str,
    filename: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> Response:
    uploaded = await chunked_upload_file(
        crm_client,
        headers,
        content=content,
        original_name=filename,
        content_type=content_type,
        spec_json=crm_entity_upload_spec_json(
            entity_id=entity_id,
            entity_type=entity_type,
            entity_title=entity_title,
        ),
        files_api_prefix=CRM_FILES_API_PREFIX,
    )
    if uploaded.status_code != 200:
        raise AssertionError(
            f"CRM chunked upload failed: {uploaded.status_code} {uploaded.text}"
        )
    upload_body = require_json_object(cast(object, uploaded.json()), "chunked complete")
    file_id = object_str(upload_body.get("file_id"), field="file_id")
    return await crm_client.post(
        f"/crm/api/v1/entities/{entity_id}/attachments",
        headers=headers,
        json={"file_id": file_id},
    )
