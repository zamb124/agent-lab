"""Prod-like: preview-share, voice-query, bulk_delete, metadata — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.operations import (
    op_flows_metadata_update,
    op_flows_nodes_bulk_delete,
    op_flows_preview_share,
    op_flows_voice_session_query,
)
from apps.flows.src.models.flow_api import (
    BulkDeleteNodesRequest,
    FlowMetadataRequest,
    FlowPreviewShareRequest,
    FlowPreviewShareResponse,
    FlowVoiceSessionQueryRequest,
)
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.types import JsonObject
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


def _two_node_body(flow_id: str, name: str) -> dict[str, object]:
    return {
        "flow_id": flow_id,
        "name": name,
        "entry": "main",
        "nodes": {
            "main": {"type": "llm_node", "prompt": "main", "tools": []},
            "extra": {"type": "llm_node", "prompt": "extra", "tools": []},
        },
        "edges": [
            {"from_node": "main", "to_node": "extra"},
            {"from_node": "extra", "to_node": None},
        ],
    }


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_voice_query_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"voice_cmd_{unique_id}"
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json=_two_node_body(flow_id, "Voice Command"),
    )
    assert created.status_code == 200, created.text
    http_res = await client.get(
        f"/flows/api/v1/flows/{flow_id}/voice-session-query",
        headers=auth_headers_system,
        params={"branch_id": "default"},
    )
    assert http_res.status_code == 200, http_res.text
    with _system_scope(system_user_id) as user:
        op_res = await op_flows_voice_session_query(
            FlowVoiceSessionQueryRequest(flow_id=flow_id, branch_id="default"),
            user=user,
            di=di,
        )
    assert op_res.model_dump(mode="json") == http_res.json()


async def test_preview_share_rest_and_op_mint_share_url(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"pshare_cmd_{unique_id}"
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json=_two_node_body(flow_id, "Preview Command"),
    )
    assert created.status_code == 200, created.text
    http_res = await client.post(
        f"/flows/api/v1/flows/{flow_id}/preview-share",
        headers=auth_headers_system,
        json={"branch_id": "default", "guest_max_user_messages": 10},
    )
    assert http_res.status_code == 200, http_res.text
    http_body = FlowPreviewShareResponse.model_validate(http_res.json())
    assert "/l/" in http_body.share_url
    with _system_scope(system_user_id) as user:
        op_res = await op_flows_preview_share(
            FlowPreviewShareRequest(
                flow_id=flow_id,
                branch_id="default",
                guest_max_user_messages=10,
            ),
            user=user,
            di=di,
        )
        with pytest.raises(WsCommandError) as missing:
            _ = await op_flows_preview_share(
                FlowPreviewShareRequest(flow_id=f"missing_{unique_id}", branch_id="default"),
                user=user,
                di=di,
            )
    branch_id = f"skill_{unique_id}"
    branched = await client.post(
        f"/flows/api/v1/{flow_id}/branches",
        headers=auth_headers_system,
        json={"branch_id": branch_id, "name": "Skill", "entry": "main"},
    )
    assert branched.status_code == 201, branched.text
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as unknown_branch:
            _ = await op_flows_preview_share(
                FlowPreviewShareRequest(flow_id=flow_id, branch_id="no_such_branch"),
                user=user,
                di=di,
            )
    assert "/l/" in op_res.share_url
    assert missing.value.code == "forbidden"
    assert unknown_branch.value.code == "ws_invalid_payload"


async def test_bulk_delete_and_metadata_rest_and_op(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    rest_id = f"editor_rest_{unique_id}"
    op_id = f"editor_op_{unique_id}"
    for flow_id in (rest_id, op_id):
        created = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json=_two_node_body(flow_id, "Editor Command"),
        )
        assert created.status_code == 200, created.text

    http_delete = await client.post(
        f"/flows/api/v1/flows/{rest_id}/nodes/bulk_delete",
        headers=auth_headers_system,
        json={"node_ids": ["extra"]},
    )
    assert http_delete.status_code == 200, http_delete.text
    with _system_scope(system_user_id) as user:
        op_delete = await op_flows_nodes_bulk_delete(
            BulkDeleteNodesRequest(flow_id=op_id, node_ids=["extra"]),
            user=user,
            di=di,
        )
    assert op_delete.model_dump(mode="json") == {
        **http_delete.json(),
        "flow_id": op_id,
    }

    notes: list[JsonObject] = [
        {"id": "n1", "x": 10, "y": 10, "width": 100, "height": 80, "text": "hi"}
    ]
    http_meta = await client.patch(
        f"/flows/api/v1/flows/{rest_id}/metadata",
        headers=auth_headers_system,
        json={"sticky_notes": notes},
    )
    assert http_meta.status_code == 200, http_meta.text
    with _system_scope(system_user_id) as user:
        op_meta = await op_flows_metadata_update(
            FlowMetadataRequest(flow_id=op_id, sticky_notes=notes),
            user=user,
            di=di,
        )
    assert op_meta.model_dump(mode="json") == {
        **http_meta.json(),
        "flow_id": op_id,
    }
    rest_item = await client.get(
        f"/flows/api/v1/flows/{rest_id}",
        headers=auth_headers_system,
    )
    op_item = await client.get(
        f"/flows/api/v1/flows/{op_id}",
        headers=auth_headers_system,
    )
    assert rest_item.status_code == 200, rest_item.text
    assert op_item.status_code == 200, op_item.text
    assert rest_item.json()["metadata"]["sticky_notes"] == notes
    assert op_item.json()["metadata"]["sticky_notes"] == notes
    assert "extra" not in rest_item.json()["nodes"]
    assert "extra" not in op_item.json()["nodes"]
    assert "main" in rest_item.json()["nodes"]
    assert "main" in op_item.json()["nodes"]
