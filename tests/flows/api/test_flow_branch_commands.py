"""Prod-like ветки: REST и `op_*` — один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.operations import (
    FlowsBranchIdPayload,
    op_flows_branch_create,
    op_flows_branch_remove,
    op_flows_branch_update,
)
from apps.flows.src.models import BranchCreateRequest, BranchUpdateRequest
from core.context import reset_context, set_context
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


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


async def test_branch_rest_and_op_share_payload(
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"branch_cmd_{unique_id}"
    created = await client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": "Branch Command",
            "entry": "main",
            "nodes": {"main": {"type": "llm_node", "prompt": "ok", "tools": []}},
            "edges": [{"from_node": "main", "to_node": None}],
        },
    )
    assert created.status_code == 200, created.text
    branch_id = f"skill_{unique_id}"
    http_create = await client.post(
        f"/flows/api/v1/{flow_id}/branches",
        headers=auth_headers_system,
        json={"branch_id": branch_id, "name": "Skill", "entry": "main"},
    )
    assert http_create.status_code == 201, http_create.text
    assert http_create.json()["branch_id"] == branch_id
    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as conflict:
            await op_flows_branch_create(
                BranchCreateRequest(
                    flow_id=flow_id,
                    branch_id=branch_id,
                    name="Skill",
                    entry="main",
                ),
                user=user,
                di=di,
            )
        assert conflict.value.code == "conflict"
        updated = await op_flows_branch_update(
            BranchUpdateRequest(
                flow_id=flow_id,
                branch_id=branch_id,
                name="Skill Updated",
                entry="main",
            ),
            user=user,
            di=di,
        )
        assert updated.branch_id == branch_id
        assert updated.status == "success"
    http_put = await client.put(
        f"/flows/api/v1/{flow_id}/branches/{branch_id}",
        headers=auth_headers_system,
        json={"name": "Skill REST", "entry": "main"},
    )
    assert http_put.status_code == 200, http_put.text
    assert http_put.json()["branch_id"] == branch_id
    with _system_scope(system_user_id) as user:
        removed = await op_flows_branch_remove(
            FlowsBranchIdPayload(flow_id=flow_id, branch_id=branch_id),
            user=user,
            di=di,
        )
        assert removed.branch_id == branch_id
    missing = await client.get(
        f"/flows/api/v1/flows/{flow_id}",
        headers=auth_headers_system,
    )
    assert missing.status_code == 200, missing.text
    assert branch_id not in missing.json()["branches"]
