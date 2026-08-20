"""llm_node tools: NodeAsTool datasource + builtin db_* on live Postgres."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from apps.flows.src.runtime.nodes import LlmNode
from core.clients.llm.mock import MockLLMQueuedResponse
from core.types import require_json_object
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.fixtures.datasources import CustomerDatasource
from tests.flows.durable_runtime_harness import run_node, workflow_state

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(120)]

MockLlmQueue = Callable[[list[MockLLMQueuedResponse]], object]


def _seed_row(customer: CustomerDatasource) -> dict[str, object]:
    return {"id": customer.seed_id, "name": customer.seed_name}


async def test_llm_node_datasource_as_tool_writes_state(
    container,
    unique_id: str,
    customer_datasource: CustomerDatasource,
    auth_headers_system: dict[str, str],
    system_user_id: str,
    mock_llm_with_queue: MockLlmQueue,
) -> None:
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "orders_query",
                "args": {"id": customer_datasource.seed_id},
            },
            {"type": "text", "content": "queried"},
        ]
    )
    node = LlmNode(
        node_id="agent",
        config={
            "type": "llm_node",
            "prompt": "Query the orders datasource.",
            "tools": [
                {
                    "tool_id": "orders_query",
                    "type": "datasource",
                    "name": "Orders query",
                    "connector_id": "postgres",
                    "datasource_id": customer_datasource.datasource_id,
                    "datasource_operation": "query",
                    "sql": customer_datasource.query_by_id_sql,
                    "input_mapping": {"id": "@state:id"},
                    "parameters_schema": {
                        "type": "object",
                        "properties": {"id": {"type": "integer"}},
                        "required": ["id"],
                    },
                }
            ],
        },
        container=container,
    )
    state = workflow_state(
        flow_id=f"ds_llm_tool_{unique_id}",
        unique_id=unique_id,
        content="query orders",
        user_id=system_user_id,
    )
    with service_client_asgi_auth_context(auth_headers_system):
        finished = await run_node(container=container, node=node, state=state)
    result = finished.datasource_result
    assert result["rows"] == [_seed_row(customer_datasource)]
    assert "orders_query" in finished.tool_results


async def test_llm_node_db_schema_query_execute_live_rows(
    container,
    unique_id: str,
    customer_datasource: CustomerDatasource,
    auth_headers_system: dict[str, str],
    system_user_id: str,
    mock_llm_with_queue: MockLlmQueue,
) -> None:
    inserted_id = customer_datasource.seed_id + 10
    inserted_name = f"llm-{unique_id}"
    mock_llm_with_queue(
        [
            {
                "type": "tool_call",
                "tool": "db_schema",
                "args": {"datasource_id": customer_datasource.datasource_id},
            },
            {
                "type": "tool_call",
                "tool": "db_query",
                "args": {
                    "datasource_id": customer_datasource.datasource_id,
                    "sql": customer_datasource.query_by_id_sql,
                    "params": {"id": customer_datasource.seed_id},
                },
            },
            {
                "type": "tool_call",
                "tool": "db_execute",
                "args": {
                    "datasource_id": customer_datasource.datasource_id,
                    "sql": customer_datasource.insert_sql,
                    "params": {"id": inserted_id, "name": inserted_name},
                },
            },
            {"type": "text", "content": "done"},
        ]
    )
    node = LlmNode(
        node_id="agent",
        config={
            "type": "llm_node",
            "prompt": "Inspect, query, then insert.",
            "tools": [
                {"tool_id": "db_schema"},
                {"tool_id": "db_query"},
                {"tool_id": "db_execute"},
            ],
        },
        container=container,
    )
    state = workflow_state(
        flow_id=f"ds_llm_db_{unique_id}",
        unique_id=unique_id,
        content="run db tools",
        user_id=system_user_id,
    )
    with service_client_asgi_auth_context(auth_headers_system):
        finished = await run_node(container=container, node=node, state=state)
    schema = require_json_object(finished.tool_results["db_schema"], "db_schema")
    tables = schema["tables"]
    if not isinstance(tables, list):
        raise AssertionError("db_schema.tables must be a list")
    table_names: list[str] = []
    for table in tables:
        table_obj = require_json_object(table, "db_schema.table")
        table_name = table_obj["table_name"]
        if not isinstance(table_name, str):
            raise AssertionError("db_schema.table_name must be str")
        table_names.append(table_name)
    assert customer_datasource.qualified_table in table_names
    queried = require_json_object(finished.tool_results["db_query"], "db_query")
    assert queried["rows"] == [_seed_row(customer_datasource)]
    executed = require_json_object(finished.tool_results["db_execute"], "db_execute")
    assert executed["rowcount"] == 1


async def test_db_execute_without_can_edit_is_denied(
    flows_client,
    auth_headers_system_user2: dict[str, str],
    customer_datasource: CustomerDatasource,
) -> None:
    denied = await flows_client.post(
        f"/flows/api/v1/datasources/{customer_datasource.datasource_id}/execute",
        headers=auth_headers_system_user2,
        json={
            "sql": customer_datasource.insert_sql,
            "params": {"id": 77, "name": "no-edit"},
        },
    )
    assert denied.status_code == 403, denied.text
