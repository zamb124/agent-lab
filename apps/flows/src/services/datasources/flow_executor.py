"""Flow-as-connector executor for DatasourceProtocol."""

from __future__ import annotations

from uuid import uuid4

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution.manager import create_initial_state
from core.context import require_context
from core.datasources.models import (
    DatasourceConnection,
    DatasourceConnectorSpec,
    DatasourceExecuteResult,
    DatasourceOperation,
    DatasourceQueryResult,
    DatasourceSchemaSnapshot,
    DatasourceTestResult,
)
from core.models.flow_interface import default_flow_interface_config
from core.types import JsonObject, require_json_object


class DatasourceFlowExecutor:
    def __init__(self, container: FlowRuntimeContainer) -> None:
        self._container: FlowRuntimeContainer = container

    async def run(
        self,
        *,
        spec: DatasourceConnectorSpec,
        connection: DatasourceConnection,
        operation: DatasourceOperation,
        sql: str | None,
        params: JsonObject,
        password: str | None,
        as_test: bool,
    ) -> (
        DatasourceSchemaSnapshot
        | DatasourceQueryResult
        | DatasourceExecuteResult
        | DatasourceTestResult
    ):
        _ = password
        flow_id = connection.flow_id or spec.flow_id
        if flow_id is None or not flow_id.strip():
            raise ValueError("flow datasource requires flow_id")
        branch_id = connection.flow_branch_id or spec.flow_branch_id
        ctx = require_context()
        context_id = f"ds-{uuid4().hex}"
        session_id = f"{flow_id}:{context_id}"
        ui_document = default_flow_interface_config().template.materialize(
            document_id=f"flow-ui:{context_id}"
        )
        state = create_initial_state(
            task_id=context_id,
            context_id=context_id,
            user_id=ctx.user.user_id,
            session_id=session_id,
            branch_id=branch_id,
            ui_document=ui_document,
        )
        state["datasource_operation"] = operation.value
        state["datasource_id"] = connection.datasource_id
        state["connector_id"] = spec.connector_id
        state["params"] = params
        state["datasource_as_test"] = as_test
        if sql is not None:
            state["sql"] = sql
        _ = await self._container.workflow_runtime.save_state(session_id, state)
        flow = await self._container.flow_factory.get_flow(flow_id, branch_id)
        if flow is None:
            raise ValueError(f"flow datasource flow not found: {flow_id}")
        finished = await flow.run(state)
        raw = finished.get("datasource_result")
        if raw is None:
            raw = finished.get("result")
        if raw is None:
            raise ValueError(
                "flow datasource must write state.datasource_result or state.result"
            )
        if as_test:
            if isinstance(raw, DatasourceTestResult):
                return raw
            return DatasourceTestResult.model_validate(
                require_json_object(raw, "flow.datasource.test")
            )
        payload = (
            raw
            if isinstance(
                raw,
                (
                    DatasourceSchemaSnapshot,
                    DatasourceQueryResult,
                    DatasourceExecuteResult,
                ),
            )
            else require_json_object(raw, "flow.datasource.result")
        )
        match operation:
            case DatasourceOperation.INTROSPECT:
                if isinstance(payload, DatasourceSchemaSnapshot):
                    return payload
                return DatasourceSchemaSnapshot.model_validate(payload)
            case DatasourceOperation.QUERY:
                if isinstance(payload, DatasourceQueryResult):
                    return payload
                return DatasourceQueryResult.model_validate(payload)
            case DatasourceOperation.EXECUTE:
                if isinstance(payload, DatasourceExecuteResult):
                    return payload
                return DatasourceExecuteResult.model_validate(payload)
