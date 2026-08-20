"""Company stamp executor=flow: protocol query runs the company flow."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.fixtures.auth import service_client_asgi_auth_context

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]

_STAMP_CODE = """
async def run(args, state):
    operation = state['datasource_operation']
    as_test = state['datasource_as_test']
    if as_test:
        state['datasource_result'] = {
            'ok': True,
            'latency_ms': 1,
            'server_version': 'stamp-flow',
        }
        return state
    if operation == 'query':
        state['datasource_result'] = {
            'columns': ['id', 'name'],
            'rows': [{'id': 1, 'name': 'stamped'}],
            'row_count': 1,
            'truncated': False,
        }
        return state
    if operation == 'introspect':
        state['datasource_result'] = {'tables': []}
        return state
    if operation == 'execute':
        state['datasource_result'] = {'rowcount': 1}
        return state
    raise ValueError('unsupported datasource_operation')
"""


async def test_flow_connector_query_writes_datasource_result(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    flow_id = f"ds_stamp_{unique_id}"
    created_flow = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": f"Datasource stamp {unique_id}",
            "entry": "stamp",
            "nodes": {
                "stamp": {
                    "type": "code",
                    "language": "python",
                    "code": _STAMP_CODE,
                }
            },
            "edges": [{"from_node": "stamp", "to_node": None}],
        },
    )
    assert created_flow.status_code == 200, created_flow.text

    connector_id = f"dsflow{unique_id}"
    upserted = await flows_client.put(
        "/flows/api/v1/datasources/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"Stamp {unique_id}",
            "description": "Flow protocol stamp",
            "executor": "flow",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["introspect", "query", "execute"],
            "flow_id": flow_id,
            "flow_branch_id": "default",
        },
    )
    assert upserted.status_code == 200, upserted.text
    assert upserted.json()["executor"] == "flow"
    assert upserted.json()["flow_id"] == flow_id

    created = await flows_client.post(
        "/flows/api/v1/datasources",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"stamp connection {unique_id}",
            "flow_id": flow_id,
        },
    )
    assert created.status_code == 200, created.text
    datasource_id = created.json()["datasource_id"]

    with service_client_asgi_auth_context(auth_headers_system):
        queried = await flows_client.post(
            f"/flows/api/v1/datasources/{datasource_id}/query",
            headers=auth_headers_system,
            json={"sql": "SELECT 1", "params": {}},
        )
    assert queried.status_code == 200, queried.text
    body = queried.json()
    assert body["columns"] == ["id", "name"]
    assert body["rows"] == [{"id": 1, "name": "stamped"}]
    assert body["row_count"] == 1
    assert body["truncated"] is False


async def test_flow_connector_test_introspect_execute(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    flow_id = f"ds_stamp_ops_{unique_id}"
    created_flow = await flows_client.post(
        "/flows/api/v1/flows/",
        headers=auth_headers_system,
        json={
            "flow_id": flow_id,
            "name": f"Datasource stamp ops {unique_id}",
            "entry": "stamp",
            "nodes": {
                "stamp": {
                    "type": "code",
                    "language": "python",
                    "code": _STAMP_CODE,
                }
            },
            "edges": [{"from_node": "stamp", "to_node": None}],
        },
    )
    assert created_flow.status_code == 200, created_flow.text

    connector_id = f"dsflop{unique_id}"
    upserted = await flows_client.put(
        "/flows/api/v1/datasources/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"Stamp ops {unique_id}",
            "description": "Flow protocol stamp ops",
            "executor": "flow",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["introspect", "query", "execute"],
            "flow_id": flow_id,
            "flow_branch_id": "default",
        },
    )
    assert upserted.status_code == 200, upserted.text

    created = await flows_client.post(
        "/flows/api/v1/datasources",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"stamp ops {unique_id}",
            "flow_id": flow_id,
            "allowed_operations": ["select", "insert", "update", "delete"],
        },
    )
    assert created.status_code == 200, created.text
    datasource_id = created.json()["datasource_id"]

    with service_client_asgi_auth_context(auth_headers_system):
        tested = await flows_client.post(
            f"/flows/api/v1/datasources/{datasource_id}/test",
            headers=auth_headers_system,
            json={},
        )
        introspected = await flows_client.post(
            f"/flows/api/v1/datasources/{datasource_id}/introspect",
            headers=auth_headers_system,
            json={},
        )
        executed = await flows_client.post(
            f"/flows/api/v1/datasources/{datasource_id}/execute",
            headers=auth_headers_system,
            json={"sql": "INSERT INTO t VALUES (1)", "params": {}},
        )
    assert tested.status_code == 200, tested.text
    assert tested.json()["ok"] is True
    assert tested.json()["server_version"] == "stamp-flow"
    assert introspected.status_code == 200, introspected.text
    assert introspected.json()["tables"] == []
    assert executed.status_code == 200, executed.text
    assert executed.json()["rowcount"] == 1


async def test_flow_connector_missing_flow_raises(
    flows_client: AsyncClient,
    auth_headers_system: dict[str, str],
    unique_id: str,
) -> None:
    connector_id = f"dsmiss{unique_id}"
    missing_flow_id = f"ds_missing_flow_{unique_id}"
    upserted = await flows_client.put(
        "/flows/api/v1/datasources/connectors",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"Missing flow {unique_id}",
            "description": "Flow id that is not in the factory",
            "executor": "flow",
            "credential_schema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
            "operations": ["query"],
            "flow_id": missing_flow_id,
            "flow_branch_id": "default",
        },
    )
    assert upserted.status_code == 200, upserted.text

    created = await flows_client.post(
        "/flows/api/v1/datasources",
        headers=auth_headers_system,
        json={
            "connector_id": connector_id,
            "name": f"missing flow {unique_id}",
            "flow_id": missing_flow_id,
        },
    )
    assert created.status_code == 200, created.text
    datasource_id = created.json()["datasource_id"]

    with service_client_asgi_auth_context(auth_headers_system):
        queried = await flows_client.post(
            f"/flows/api/v1/datasources/{datasource_id}/query",
            headers=auth_headers_system,
            json={"sql": "SELECT 1", "params": {}},
        )
    assert queried.status_code == 400, queried.text
    assert "flow not found" in queried.text
