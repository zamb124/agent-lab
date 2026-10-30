"""Standalone graph: entry → datasource → exact customer rows."""

from __future__ import annotations

import pytest

from apps.flows.src.flow_ui.templates import default_chat_document
from apps.flows.src.models import Edge
from apps.flows.src.runtime.execution_context import execution_context_for
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import DatasourceNode
from tests.fixtures.auth import service_client_asgi_auth_context
from tests.fixtures.datasources import CustomerDatasource
from tests.flows.durable_runtime_harness import run_flow, workflow_state

pytestmark = [pytest.mark.asyncio, pytest.mark.timeout(60)]


async def test_datasource_standalone_flow_query_exact_rows(
    di,
    unique_id: str,
    customer_datasource: CustomerDatasource,
    auth_headers_system: dict[str, str],
) -> None:
    flow_id = f"ds_standalone_{unique_id}"
    node = DatasourceNode(
        node_id="orders",
        config={
            "type": "datasource",
            "connector_id": "postgres",
            "datasource_id": customer_datasource.datasource_id,
            "datasource_operation": "query",
            "sql": customer_datasource.query_by_id_sql,
            "input_mapping": {"id": "@state:item_id"},
        },
        execution=execution_context_for(di.node_constructor.workflow_runtime), redis_client=di.node_constructor.redis_client, datasource_service=di.node_constructor.datasource_service, datasource_executors=di.datasource_executors,
    )
    flow = Flow(
        flow_id=flow_id,
        name="Datasource standalone",
        entry="orders",
        nodes={"orders": node},
        edges=[Edge(from_node="orders", to_node=None)],
        interface=default_chat_document(),
        execution=execution_context_for(di.node_constructor.workflow_runtime), emitter_factory=di.node_constructor.emitter_factory,
    )
    state = workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        item_id=customer_datasource.seed_id,
    )
    with service_client_asgi_auth_context(auth_headers_system):
        finished = await run_flow(di=di, flow=flow, state=state)
    result = finished.datasource_result
    assert result["columns"] == ["id", "name"]
    assert result["rows"] == [
        {"id": customer_datasource.seed_id, "name": customer_datasource.seed_name}
    ]
    assert result["row_count"] == 1
    assert result["truncated"] is False
    assert finished.result == result
