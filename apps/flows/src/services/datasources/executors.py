"""Исполнители MCP- и flow-коннекторов datasource для runtime flows."""

from __future__ import annotations

from apps.flows.src.contracts import FlowFactoryProtocol, ToolRegistryProtocol
from apps.flows.src.durable_execution.manager import DurableWorkflowRuntime
from apps.flows.src.services.datasources.flow_executor import DatasourceFlowExecutor
from apps.flows.src.services.datasources.mcp_executor import DatasourceMcpExecutor
from core.datasources.service import DatasourceExecutors


def build_datasource_executors(
    *,
    workflow_runtime: DurableWorkflowRuntime,
    flow_factory: FlowFactoryProtocol,
    tool_registry: ToolRegistryProtocol,
) -> DatasourceExecutors:
    return DatasourceExecutors(
        mcp=DatasourceMcpExecutor(),
        flow=DatasourceFlowExecutor(
            workflow_runtime=workflow_runtime,
            flow_factory=flow_factory,
            tool_registry=tool_registry,
        ),
    )
