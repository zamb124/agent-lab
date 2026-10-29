"""Company stamp executor=mcp: protocol uses MCP stub structuredContent."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from tests.fixtures.mcp_modes_stub import MCPStubMode

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]

_TOOL_NAME = "ds_proto"


def _tool_result(structured: dict[str, object]) -> dict[str, object]:
    return {
        "content": [{"type": "text", "text": "{}"}],
        "isError": False,
        "structuredContent": structured,
    }


async def test_mcp_connector_test_introspect_query_execute(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    mcp_modes_stub,
    unique_id: str,
) -> None:
    url, state = mcp_modes_stub(
        MCPStubMode(
            tools=[
                {
                    "name": _TOOL_NAME,
                    "description": "Datasource protocol stub",
                    "inputSchema": {"type": "object", "properties": {}},
                }
            ],
            tool_call_result=_tool_result({"tables": []}),
        )
    )
    server_id = f"dsm{unique_id}"
    created_server = await flows_client.post(
        "/flows/api/v1/mcp/servers",
        headers=auth_headers_system,
        json={
            "server_id": server_id,
            "name": f"Datasource MCP {unique_id}",
            "url": url,
            "transport_type": "http",
        },
    )
    assert created_server.status_code == 200, created_server.text

    connector_id = f"dsmc{unique_id}"
    upserted = await flows_client.put(
        "/flows/api/v1/datasources/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"MCP stamp {unique_id}",
            "description": "MCP protocol stamp",
            "executor": "mcp",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["introspect", "query", "execute"],
            "mcp_server_id": server_id,
            "mcp_query_tool": _TOOL_NAME,
            "mcp_execute_tool": _TOOL_NAME,
        },
    )
    assert upserted.status_code == 200, upserted.text
    assert upserted.json()["executor"] == "mcp"

    created = await flows_client.post(
        "/flows/api/v1/datasources",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"mcp connection {unique_id}",
            "mcp_server_id": server_id,
            "allowed_operations": ["select", "insert", "update", "delete"],
        },
    )
    assert created.status_code == 200, created.text
    datasource_id = created.json()["datasource_id"]

    tested = await flows_client.post(
        f"/flows/api/v1/datasources/{datasource_id}/test",
        headers=auth_headers_system,
        json={},
    )
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True

    state.mode.tool_call_result = _tool_result({"tables": []})
    introspected = await flows_client.post(
        f"/flows/api/v1/datasources/{datasource_id}/introspect",
        headers=auth_headers_system,
        json={},
    )
    assert introspected.status_code == 200, introspected.text
    assert introspected.json()["tables"] == []

    state.mode.tool_call_result = _tool_result(
        {
            "columns": ["id"],
            "rows": [{"id": 1}],
            "row_count": 1,
            "truncated": False,
        }
    )
    queried = await flows_client.post(
        f"/flows/api/v1/datasources/{datasource_id}/query",
        headers=auth_headers_system,
        json={"sql": "SELECT 1", "params": {}},
    )
    assert queried.status_code == 200, queried.text
    query_body = queried.json()
    assert query_body["columns"] == ["id"]
    assert query_body["rows"] == [{"id": 1}]
    assert query_body["row_count"] == 1
    assert query_body["truncated"] is False

    state.mode.tool_call_result = _tool_result({"rowcount": 2})
    executed = await flows_client.post(
        f"/flows/api/v1/datasources/{datasource_id}/execute",
        headers=auth_headers_system,
        json={"sql": "INSERT INTO t VALUES (1)", "params": {}},
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["rowcount"] == 2

    deleted = await flows_client.delete(
        f"/flows/api/v1/mcp/servers/{server_id}",
        headers=auth_headers_system,
    )
    assert deleted.status_code in {200, 204}, deleted.text
