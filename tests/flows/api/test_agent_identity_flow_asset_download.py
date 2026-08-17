"""Public flow_asset download without auth (AgentIdentity embed <img>)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.files.chunked_upload_helpers import (
    chunked_upload_file,
    flow_asset_upload_spec_json,
)
from tests.fixtures.s3 import require_s3_configured

FLOWS_FILES_PREFIX = "/flows/api/v1/files"


@pytest.mark.asyncio
async def test_public_flow_asset_download_without_auth(
    flows_client: AsyncClient, embed_test_auth
) -> None:
    require_s3_configured()
    auth_headers, flow_id, _, _ = embed_test_auth
    content = b"agent-identity-public-bytes"
    upload = await chunked_upload_file(
        flows_client,
        auth_headers,
        content=content,
        original_name="agent.png",
        content_type="image/png",
        spec_json=flow_asset_upload_spec_json(flow_id=flow_id, is_public=True),
        files_api_prefix=FLOWS_FILES_PREFIX,
    )
    assert upload.status_code == 200, upload.text
    payload = upload.json()
    assert payload["is_public"] is True
    file_id = payload["file_id"]

    anonymous = await flows_client.get(f"{FLOWS_FILES_PREFIX}/download/{file_id}")
    assert anonymous.status_code == 200
    assert anonymous.content == content


@pytest.mark.asyncio
async def test_private_flow_asset_download_without_auth_403(
    flows_client: AsyncClient, embed_test_auth
) -> None:
    require_s3_configured()
    auth_headers, flow_id, _, _ = embed_test_auth
    content = b"agent-identity-private-bytes"
    upload = await chunked_upload_file(
        flows_client,
        auth_headers,
        content=content,
        original_name="agent-private.png",
        content_type="image/png",
        spec_json=flow_asset_upload_spec_json(flow_id=flow_id, is_public=False),
        files_api_prefix=FLOWS_FILES_PREFIX,
    )
    assert upload.status_code == 200, upload.text
    payload = upload.json()
    assert payload["is_public"] is False
    file_id = payload["file_id"]

    anonymous = await flows_client.get(f"{FLOWS_FILES_PREFIX}/download/{file_id}")
    assert anonymous.status_code == 403

    authorized = await flows_client.get(
        f"{FLOWS_FILES_PREFIX}/download/{file_id}",
        headers=auth_headers,
    )
    assert authorized.status_code == 200
    assert authorized.content == content
