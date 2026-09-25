"""Prod-like: code_agent — REST и `op_*` один handler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager

import pytest
from httpx import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.realtime.code_agent_operations import (
    op_flows_code_agent_ensure_source,
    op_flows_code_agent_rebuild,
    op_flows_code_agent_status,
)
from core.context import reset_context, set_context
from core.guest_runtime.models import (
    CodeAgentEnsureSourceResponse,
    CodeAgentNodeRefPayload,
    CodeAgentNodeStatusResponse,
    CodeAgentRebuildRequest,
    GuestInvokeKind,
    GuestLanguage,
)
from core.models.context_models import Context
from core.models.identity_models import User
from core.websocket import WsCommandError
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.fixtures.s3 import require_s3_configured
from tests.guest_runtime.http_helpers import (
    code_agent_headers,
    create_code_agent_flow,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(90)]


@contextmanager
def _system_scope(system_user_id: str) -> Generator[User]:
    user = User(user_id=system_user_id, name="System")
    token = set_context(
        Context(
            user=user,
            active_company=make_test_company(company_id="system", name="System"),
            channel="api",
            active_namespace="default",
        )
    )
    try:
        yield user
    finally:
        reset_context(token)


async def test_code_agent_ensure_and_status_rest_match_op(
    client: AsyncClient,
    di: FlowsDi,
    office_service: object,
    guest_runtime_service: object,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    _ = office_service, guest_runtime_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_cmd_{unique_id}"
    node_id = "agent"
    await create_code_agent_flow(
        client,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python", "main.py"],
    )

    ensure_http = await client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/ensure-source",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert ensure_http.status_code == 200, ensure_http.text
    ensured = CodeAgentEnsureSourceResponse.model_validate(ensure_http.json())
    assert ensured.flow_id == flow_id
    assert ensured.node_id == node_id
    assert ensured.catalog_id != ""

    status_http = await client.get(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert status_http.status_code == 200, status_http.text
    status = CodeAgentNodeStatusResponse.model_validate(status_http.json())
    assert status.catalog_id == ensured.catalog_id

    with _system_scope(system_user_id) as user:
        ref = CodeAgentNodeRefPayload(flow_id=flow_id, node_id=node_id, branch_id="default")
        op_ensured = await op_flows_code_agent_ensure_source(ref, user=user, di=di)
        assert op_ensured.model_dump(mode="json") == ensure_http.json()
        op_status = await op_flows_code_agent_status(ref, user=user, di=di)
        assert op_status.model_dump(mode="json") == status_http.json()

    missing = await client.get(
        f"/flows/api/v1/flows/missing-{unique_id}/nodes/{node_id}/code-agent",
        headers=headers,
    )
    assert missing.status_code == 403, missing.text
    assert missing.json()["error_code"] == "forbidden"

    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_flows_code_agent_status(
                CodeAgentNodeRefPayload(
                    flow_id=f"missing-{unique_id}",
                    node_id=node_id,
                    branch_id="default",
                ),
                user=user,
                di=di,
            )
    assert exc_info.value.code == "forbidden"

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)


async def test_code_agent_rebuild_empty_argv_via_op(
    client: AsyncClient,
    di: FlowsDi,
    office_service: object,
    unique_id: str,
    system_user_id: str,
    auth_headers_system: dict[str, str],
) -> None:
    _ = office_service
    require_s3_configured()
    headers = code_agent_headers(auth_headers_system)
    flow_id = f"ca_cmd_argv_{unique_id}"
    node_id = "agent"
    await create_code_agent_flow(
        client,
        headers,
        flow_id=flow_id,
        node_id=node_id,
        invoke_argv=["python", "main.py"],
    )
    ensure_http = await client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/ensure-source",
        headers=headers,
        params={"branch_id": "default"},
    )
    assert ensure_http.status_code == 200, ensure_http.text

    rebuild_http = await client.post(
        f"/flows/api/v1/flows/{flow_id}/nodes/{node_id}/code-agent/rebuild",
        headers=headers,
        params={"branch_id": "default"},
        json={
            "language": "python",
            "invoke_kind": "cli",
            "invoke_argv": [],
        },
    )
    assert rebuild_http.status_code == 400, rebuild_http.text

    with _system_scope(system_user_id) as user:
        with pytest.raises(WsCommandError) as exc_info:
            _ = await op_flows_code_agent_rebuild(
                CodeAgentRebuildRequest(
                    flow_id=flow_id,
                    node_id=node_id,
                    branch_id="default",
                    language=GuestLanguage.PYTHON,
                    invoke_kind=GuestInvokeKind.CLI,
                    invoke_argv=[],
                ),
                user=user,
                di=di,
            )
    assert exc_info.value.code == "ws_invalid_payload"

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=headers)
