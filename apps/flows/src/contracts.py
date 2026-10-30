"""Структурные контракты runtime flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Protocol, TypeAlias, TypedDict

from core.mail.service import MailService
from core.types import JsonObject, JsonValue
from core.ui_document.document import FlowUIDocument

if TYPE_CHECKING:
    from apps.flows.src.models import (
        BranchConfig,
        FlowConfig,
        FlowToolReference,
        NodeConfig,
        ResourceMapInput,
        ToolReference,
        TriggerConfig,
    )
    from apps.flows.src.models.enums import ChannelType, NodeType
    from apps.flows.src.models.evaluation_lab import (
        EvaluationGatePolicyRunRequest,
        EvaluationMonitorCycleRequest,
        EvaluationMonitorCycleResult,
        EvaluationRunJob,
        EvaluationRunWithCases,
        EvaluationTaskiqExecutionContext,
    )
    from apps.flows.src.models.flow_config import Edge
    from apps.flows.src.state import ExecutionState
    from apps.flows.src.tools.base import BaseTool
    from core.mail.service import MailService


class EffectiveFlowConfig(TypedDict):
    entry: str | None
    nodes: dict[str, "FlowNodeRuntimeConfig"]
    edges: list[Edge]
    variables: JsonObject


FlowNodeRuntimeConfig: TypeAlias = JsonObject


class RuntimeFlowConfig(TypedDict, total=False):
    version: JsonValue
    nodes: dict[str, FlowNodeRuntimeConfig]


class RuntimeFlowProtocol(Protocol):
    entry: str
    variables: JsonObject
    config: JsonObject
    interface: FlowUIDocument

    async def run(self, state: ExecutionState) -> ExecutionState: ...


class RuntimeNodeProtocol(Protocol):
    config: JsonObject
    run: Callable[["ExecutionState"], Awaitable["ExecutionState"]]


class RuntimeNodeClassProtocol(Protocol):
    """Класс ноды, который реестр отдаёт по NodeType."""


class NodeRegistryProtocol(Protocol):
    def get(self, key: str | NodeType) -> RuntimeNodeClassProtocol: ...


class ToolRegistryProtocol(Protocol):
    def get(self, name: str) -> BaseTool | None: ...

    def register_builtin_tools(self) -> None: ...

    async def materialize(
        self,
        tool_ref: JsonObject | FlowToolReference | ToolReference | NodeConfig,
    ) -> BaseTool: ...

    async def create_tool(
        self,
        tool_ref: str | JsonObject | FlowToolReference | ToolReference | NodeConfig,
    ) -> BaseTool: ...

    async def create_tools(
        self,
        tool_refs: Sequence[str | JsonObject | FlowToolReference | ToolReference | NodeConfig],
    ) -> list[BaseTool]: ...


class ChannelActionHandlerProtocol(Protocol):
    async def execute_action(
        self,
        action: str,
        params: JsonObject,
        config: JsonObject,
        variables: JsonObject,
        state: ExecutionState | JsonObject | None = None,
    ) -> JsonObject: ...


class ChannelRegistryProtocol(Protocol):
    def get(
        self,
        channel_type: ChannelType | str,
        *,
        mail_service: MailService | None = None,
    ) -> ChannelActionHandlerProtocol: ...


class FlowFactoryProtocol(Protocol):
    async def get_flow_config_snapshot(
        self,
        flow_id: str,
        config_version: str | None = None,
    ) -> FlowConfig | None: ...

    async def get_flow(
        self,
        flow_id: str,
        branch_id: str = "default",
        config_version: str | None = None,
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol | None: ...

    async def get_resource_maps(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> tuple[ResourceMapInput, ResourceMapInput | None]: ...

    async def get_effective_nodes_map(
        self,
        flow_id: str,
        branch_id: str,
        config_version: str | None = None,
    ) -> dict[str, FlowNodeRuntimeConfig]: ...

    async def get_resolved_variables_map(
        self,
        flow_id: str,
        branch_id: str = "default",
        *,
        config_version: str | None = None,
    ) -> JsonObject: ...

    async def create_validation_flow(
        self,
        config: JsonObject,
        *,
        tool_registry: ToolRegistryProtocol,
    ) -> RuntimeFlowProtocol: ...

    def apply_branch(self, config: FlowConfig, branch_id: str) -> EffectiveFlowConfig: ...

    async def get_branches(self, flow_id: str) -> dict[str, BranchConfig]: ...


class TriggerRegistryProtocol(Protocol):
    async def sync_triggers(
        self,
        flow_id: str,
        old_config: FlowConfig | None,
        new_config: FlowConfig,
    ) -> FlowConfig: ...

    async def reregister_trigger(
        self,
        flow_id: str,
        trigger: TriggerConfig,
    ) -> TriggerConfig: ...


class EvaluationLabServiceProtocol(Protocol):
    async def create_run_job(
        self,
        run_id: str,
        *,
        context_data: JsonObject,
        trace_context: JsonObject | None,
    ) -> EvaluationRunJob: ...

    async def get_run_job(self, run_id: str) -> EvaluationRunJob: ...

    async def list_pending_run_jobs(self, limit: int) -> list[EvaluationRunJob]: ...

    async def mark_run_job_enqueued(self, run_id: str) -> EvaluationRunJob: ...

    async def mark_run_job_failed(self, run_id: str, error: str) -> EvaluationRunJob: ...

    async def mark_run_enqueue_failed(
        self,
        run_id: str,
        error: str,
    ) -> EvaluationRunWithCases: ...

    async def execute_run_from_taskiq(
        self,
        run_id: str,
        execution: EvaluationTaskiqExecutionContext,
    ) -> EvaluationRunWithCases: ...

    async def get_run(self, run_id: str) -> EvaluationRunWithCases: ...

    async def create_gate_policy_run(
        self,
        gate_policy_id: str,
        request: EvaluationGatePolicyRunRequest,
    ) -> EvaluationRunWithCases: ...

    async def run_monitor_cycle(
        self,
        monitor_id: str,
        request: EvaluationMonitorCycleRequest,
    ) -> EvaluationMonitorCycleResult: ...


