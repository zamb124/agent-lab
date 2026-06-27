"""
Оркестрация agent-to-agent handoff/handback на channel layer.

Запуск child flow, маршрутизация пользовательских сообщений и auto-resume parent после handback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from apps.flows.config import get_settings
from apps.flows.src.channels.types import FlowExecutionTarget, PreparedTaskParams
from apps.flows.src.db import FlowRepository
from apps.flows.src.durable_execution import (
    DurableWorkflowRuntime,
    FlowHandbackCompletedPayload,
    FlowHandoffInitiatedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.models.enums import NodeType
from apps.flows.src.runtime.a2a_messages import build_tool_result_message
from apps.flows.src.services.handoff_context_service import (
    HandoffContextService,
    handoff_context_resource_key_from_body,
)
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming.emitter import Emitter
from apps.flows.src.tasks.task_names import TASK_PROCESS_FLOW
from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema
from apps.flows.src.tracing.handoff_tracing import (
    HANDBACK_OP_COMPLETED,
    continue_handoff_trace_context,
    fork_handoff_trace_context,
    handoff_span_attributes,
    trace_context_to_kiq_payload,
)
from apps.flows_worker.broker_core import broker as flows_broker
from core.clients.redis_client import RedisClient
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import HandoffInterrupt, InterruptKind
from core.tasks.kicker import kiq_task_name_with_context
from core.tracing.context import TraceContext
from core.tracing.operation_span import traced_operation
from core.types import JsonObject

logger = get_logger(__name__)


@dataclass(frozen=True)
class HandoffRouting:
    child_session_id: str
    child_flow_id: str
    child_branch_id: str


class HandoffOrchestratorService:
    _workflow_runtime: DurableWorkflowRuntime
    _flow_repository: FlowRepository
    _redis: RedisClient
    _handoff_context_service: HandoffContextService

    def __init__(
        self,
        *,
        workflow_runtime: DurableWorkflowRuntime,
        flow_repository: FlowRepository,
        redis_client: RedisClient,
        handoff_context_service: HandoffContextService,
    ) -> None:
        self._workflow_runtime = workflow_runtime
        self._flow_repository = flow_repository
        self._redis = redis_client
        self._handoff_context_service = handoff_context_service

    @staticmethod
    def build_child_session_ids(
        parent_context_id: str,
        target_flow_id: str,
    ) -> tuple[str, str]:
        child_context_id = f"{parent_context_id}:handoff:{target_flow_id}"
        child_session_id = f"{target_flow_id}:{child_context_id}"
        return child_context_id, child_session_id

    async def validate_handoff_target(self, body: HandoffInterrupt) -> HandoffInterrupt:
        if body.target_kind == "external":
            if body.remote_flow_id is None:
                raise ValueError("external handoff requires remote_flow_id")
            remote_config = await self._flow_repository.get(body.remote_flow_id)
            if remote_config is None:
                raise ValueError(f"remote flow not found: {body.remote_flow_id}")
            return body.model_copy(update={"target_name": remote_config.name})
        flow_config = await self._flow_repository.get(body.target_flow_id)
        if flow_config is None:
            raise ValueError(
                f"target flow not found: {body.target_flow_id} "
                + "(dependency flow не установлен в компании; для bundle-агентов — "
                + "reload-from-bundle родителя с depends_on_flow_ids)"
            )
        return body.model_copy(update={"target_name": flow_config.name})

    def assert_handoff_depth_allowed(self, parent_state: ExecutionState) -> int:
        child_depth = parent_state.handoff_depth + 1
        max_depth = get_settings().handoff_max_depth
        if child_depth > max_depth:
            raise ValueError(
                f"handoff_max_depth exceeded: {child_depth} > {max_depth}"
            )
        return child_depth

    async def resolve_execution_target(
        self,
        *,
        parent_flow_id: str,
        params: PreparedTaskParams,
    ) -> FlowExecutionTarget:
        if not params.is_handoff_user_reply:
            return FlowExecutionTarget(
                flow_id=parent_flow_id,
                session_id=params.session_id,
                context_id=params.context_id,
                branch_id=params.branch_id,
                is_resume=params.is_resume,
            )
        if params.handoff_child_flow_id is None or params.handoff_child_session_id is None:
            raise ValueError("handoff user reply requires child routing fields")
        child_state = await self._workflow_runtime.get_state(params.handoff_child_session_id)
        if child_state is None:
            raise ValueError(
                f"child state not initialized: {params.handoff_child_session_id}"
            )
        child_branch_id = params.handoff_child_branch_id or child_state.branch_id
        return FlowExecutionTarget(
            flow_id=params.handoff_child_flow_id,
            session_id=params.handoff_child_session_id,
            context_id=child_state.context_id,
            branch_id=child_branch_id,
            is_resume=bool(child_state.interrupt or child_state.breakpoint_hit),
        )

    def resolve_active_handoff_child(self, state: ExecutionState) -> HandoffRouting | None:
        if state.interrupt is None:
            return None
        if state.interrupt.body.kind != InterruptKind.HANDOFF:
            return None
        body = state.interrupt.body
        for link in state.child_workflows.values():
            if not link.handoff:
                continue
            if link.status not in ("running", "suspended"):
                continue
            return HandoffRouting(
                child_session_id=link.child_session_id,
                child_flow_id=link.child_flow_id,
                child_branch_id=link.child_flow_branch_id,
            )
        for item in state.interrupt_path:
            if item.child_session_id and item.child_flow_id:
                branch_id = item.child_flow_branch_id or body.target_branch_id
                return HandoffRouting(
                    child_session_id=item.child_session_id,
                    child_flow_id=item.child_flow_id,
                    child_branch_id=branch_id,
                )
        return None

    async def ensure_child_state(
        self,
        *,
        parent_state: ExecutionState,
        parent_params: PreparedTaskParams,
        body: HandoffInterrupt,
        child_session_id: str,
        child_context_id: str,
        child_depth: int,
    ) -> ExecutionState:
        existing = await self._workflow_runtime.get_state(child_session_id)
        if existing is not None:
            return existing

        child_task_id = str(uuid.uuid4())
        initial_content = parent_state.content
        if not initial_content:
            initial_content = body.reason or body.question

        child_state = create_initial_state(
            task_id=child_task_id,
            context_id=child_context_id,
            user_id=parent_state.user_id,
            session_id=child_session_id,
            content=initial_content,
            branch_id=body.target_branch_id,
        )
        child_state.user_groups = list(parent_state.user_groups)
        child_state.variables = dict(body.variables)
        child_state.handoff_parent_session_id = parent_params.session_id
        child_state.handoff_depth = child_depth
        if parent_state.handoff_trace_id is not None:
            child_state.handoff_trace_id = parent_state.handoff_trace_id

        child_state = await self._apply_handoff_context_resource(
            parent_state=parent_state,
            child_state=child_state,
            body=body,
        )

        _ = await self._workflow_runtime.save_state(
            child_session_id,
            child_state,
            event_type=WorkflowEventType.state_projection_committed,
            payload=None,
            snapshot=True,
        )
        return child_state

    async def record_handoff_initiated(
        self,
        *,
        parent_session_id: str,
        parent_state: ExecutionState,
        body: HandoffInterrupt,
        child_session_id: str,
        child_depth: int,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> None:
        _ = await self._workflow_runtime.save_state(
            parent_session_id,
            parent_state,
            event_type=WorkflowEventType.handoff_initiated,
            payload=FlowHandoffInitiatedPayload(
                parent_session_id=parent_session_id,
                child_session_id=child_session_id,
                target_flow_id=body.target_flow_id,
                target_branch_id=body.target_branch_id,
                variables=dict(body.variables),
                handoff_depth=child_depth,
                trace_id=trace_id,
                span_id=span_id,
            ),
        )

    async def kickoff_child_flow(
        self,
        *,
        parent_params: PreparedTaskParams,
        parent_state: ExecutionState,
        body: HandoffInterrupt,
        child_session_id: str,
        child_context_id: str,
        child_depth: int,
        channel_name: str,
        context_data: JsonObject,
        trace_context: TraceContext | None = None,
    ) -> None:
        _ = await self.ensure_child_state(
            parent_state=parent_state,
            parent_params=parent_params,
            body=body,
            child_session_id=child_session_id,
            child_context_id=child_context_id,
            child_depth=child_depth,
        )
        child_state = await self._workflow_runtime.get_state(child_session_id)
        if child_state is None:
            raise ValueError(f"child state not initialized: {child_session_id}")

        child_trace_payload: JsonObject | None = None
        if trace_context is not None:
            child_trace = fork_handoff_trace_context(
                trace_context,
                session_agent=child_session_id,
                flow_id=body.target_flow_id,
                branch_id=body.target_branch_id,
                task_id=child_state.task_id,
                context_id=child_context_id,
                channel=channel_name,
                is_resume=False,
            )
            child_trace_payload = trace_context_to_kiq_payload(child_trace)

        _ = await kiq_task_name_with_context(
            TASK_PROCESS_FLOW,
            flows_broker,
            flow_id=body.target_flow_id,
            session_id=child_session_id,
            user_id=parent_state.user_id,
            content=child_state.content,
            branch_id=body.target_branch_id,
            channel=channel_name,
            task_id=child_state.task_id,
            context_id=child_context_id,
            metadata={},
            is_resume=False,
            files=[],
            context_data=context_data,
            trace_context=child_trace_payload,
            background_kind="flow_handoff_child",
        )
        logger.info(
            "handoff.child.kicked",
            parent_session_id=parent_params.session_id,
            child_session_id=child_session_id,
            target_flow_id=body.target_flow_id,
            trace_id=parent_state.handoff_trace_id,
        )

    @staticmethod
    def _handoff_tool_node_id(parent_state: ExecutionState) -> str:
        for item in parent_state.interrupt_path:
            if item.node_type == NodeType.LLM_NODE.value:
                return item.node_id
        if parent_state.current_nodes:
            return parent_state.current_nodes[0]
        return "main"

    async def complete_handback(
        self,
        *,
        child_state: ExecutionState,
        channel_name: str,
        context_data: JsonObject,
        trace_context: TraceContext | None = None,
    ) -> None:
        parent_session_id = child_state.handoff_parent_session_id
        if parent_session_id is None:
            raise ValueError("handback requires handoff_parent_session_id on child state")

        handoff_trace_id = child_state.handoff_trace_id
        span_attrs = handoff_span_attributes(
            phase="completed",
            parent_session_id=parent_session_id,
            child_session_id=child_state.session_id,
            target_flow_id=child_state.session_flow_id,
            depth=child_state.handoff_depth,
            trace_id=handoff_trace_id,
        )
        async with traced_operation(
            HANDBACK_OP_COMPLETED,
            extra_attributes=span_attrs,
        ):
            await self._complete_handback_impl(
                child_state=child_state,
                channel_name=channel_name,
                context_data=context_data,
                trace_context=trace_context,
                parent_session_id=parent_session_id,
            )

    async def _complete_handback_impl(
        self,
        *,
        child_state: ExecutionState,
        channel_name: str,
        context_data: JsonObject,
        trace_context: TraceContext | None,
        parent_session_id: str,
    ) -> None:
        parent_state = await self._workflow_runtime.get_state(parent_session_id)
        if parent_state is None:
            raise ValueError(f"parent state not found for handback: {parent_session_id}")

        handback_response = child_state.response
        if not handback_response:
            raise ValueError("handback requires non-empty response on child state")

        handback_variables = await self._validate_handback_variables(
            child_state,
            dict(child_state.handback_return_variables),
        )

        parent_flow_id = parent_session_id.split(":", 1)[0]
        tool_call = (
            parent_state.interrupt.system.tool_call
            if parent_state.interrupt is not None
            else None
        )
        source_node_id = self._handoff_tool_node_id(parent_state)
        if tool_call is not None:
            parent_state.messages.append(
                build_tool_result_message(
                    tool_call.id,
                    handback_response,
                    source_node_id,
                    context_id=parent_state.context_id,
                    task_id=parent_state.task_id,
                )
            )

        for link in parent_state.child_workflows.values():
            if link.child_session_id == child_state.session_id:
                link.status = "completed"
                break

        if parent_state.handoff_depth > 0:
            parent_state.handoff_depth -= 1

        InterruptManager.prepare_handback_resume(
            parent_state,
            handback_response,
            handback_variables,
        )
        parent_state.interrupt_path = []

        handoff_trace_id = child_state.handoff_trace_id or parent_state.handoff_trace_id

        _ = await self._workflow_runtime.save_state(
            parent_session_id,
            parent_state,
            event_type=WorkflowEventType.handback_completed,
            payload=FlowHandbackCompletedPayload(
                parent_session_id=parent_session_id,
                child_session_id=child_state.session_id,
                child_flow_id=child_state.session_flow_id,
                response=handback_response,
                variables=handback_variables,
                handoff_depth=child_state.handoff_depth,
                trace_id=handoff_trace_id,
            ),
        )

        parent_flow_config = await self._flow_repository.get(parent_flow_id)
        parent_flow_name = parent_flow_id
        if parent_flow_config is not None:
            parent_flow_name = parent_flow_config.name

        child_flow_config = await self._flow_repository.get(child_state.session_flow_id)
        child_flow_name = child_state.session_flow_id
        if child_flow_config is not None:
            child_flow_name = child_flow_config.name

        parent_emitter = Emitter(self._redis, parent_state)
        await parent_emitter.emit_handback_completed(
            response=handback_response,
            handoff_depth=child_state.handoff_depth,
            child_flow_id=child_state.session_flow_id,
            child_flow_name=child_flow_name,
            parent_flow_name=parent_flow_name,
            trace_id=handoff_trace_id,
        )

        parent_trace_payload: JsonObject | None = None
        if trace_context is not None:
            parent_trace = fork_handoff_trace_context(
                trace_context,
                session_agent=parent_session_id,
                flow_id=parent_flow_id,
                branch_id=parent_state.branch_id,
                task_id=parent_state.task_id,
                context_id=parent_state.context_id,
                channel=channel_name,
                is_resume=True,
            )
            parent_trace_payload = trace_context_to_kiq_payload(parent_trace)
        elif handoff_trace_id is not None:
            parent_trace = continue_handoff_trace_context(
                handoff_trace_id,
                user_id=parent_state.user_id,
                session_agent=parent_session_id,
                flow_id=parent_flow_id,
                branch_id=parent_state.branch_id,
                task_id=parent_state.task_id,
                context_id=parent_state.context_id,
                channel=channel_name,
                is_resume=True,
            )
            parent_trace_payload = trace_context_to_kiq_payload(parent_trace)

        _ = await kiq_task_name_with_context(
            TASK_PROCESS_FLOW,
            flows_broker,
            flow_id=parent_flow_id,
            session_id=parent_session_id,
            user_id=parent_state.user_id,
            content=handback_response,
            branch_id=parent_state.branch_id,
            channel=channel_name,
            task_id=parent_state.task_id,
            context_id=parent_state.context_id,
            metadata={},
            is_resume=False,
            files=[],
            context_data=context_data,
            trace_context=parent_trace_payload,
            background_kind="flow_handback_parent",
        )
        logger.info(
            "handoff.parent.resume_kicked",
            parent_session_id=parent_session_id,
            child_session_id=child_state.session_id,
            trace_id=handoff_trace_id,
        )

    async def _apply_handoff_context_resource(
        self,
        *,
        parent_state: ExecutionState,
        child_state: ExecutionState,
        body: HandoffInterrupt,
    ) -> ExecutionState:
        resource_key = handoff_context_resource_key_from_body(body)
        return await self._handoff_context_service.apply_to_child_state(
            parent_state=parent_state,
            child_state=child_state,
            _body=body,
            resource_key=resource_key,
        )

    async def _validate_handback_variables(
        self,
        child_state: ExecutionState,
        variables: JsonObject,
    ) -> JsonObject:
        if not variables:
            return variables
        flow_config = await self._flow_repository.get(child_state.session_flow_id)
        if flow_config is None:
            raise ValueError(
                "child flow config not found for handback validation: "
                + f"{child_state.session_flow_id}"
            )
        entry_node_id = flow_config.entry
        if entry_node_id is None:
            raise ValueError(
                f"child flow {child_state.session_flow_id!r} has no entry for handback schema"
            )
        if flow_config.nodes is None:
            raise ValueError(
                f"child flow {child_state.session_flow_id!r} has no nodes for handback schema"
            )
        entry_node = flow_config.nodes.get(entry_node_id)
        if entry_node is None:
            raise ValueError(
                f"entry node {entry_node_id!r} not found in flow {child_state.session_flow_id!r}"
            )
        raw_schema = entry_node.get("output_schema")
        if raw_schema is None:
            return variables
        if not isinstance(raw_schema, dict):
            raise ValueError(
                f"entry node output_schema must be object in flow {child_state.session_flow_id!r}"
            )
        validate_tool_args_against_parameters_schema(
            schema=raw_schema,
            arguments=variables,
        )
        return variables
