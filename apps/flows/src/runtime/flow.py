"""
Flow - выполнение графа нод.

Архитектура:
- nodes: ноды (llm_node, function, flow)
- edges: связи между нодами с условиями
- entry: точка входа

Выполнение:
1. Начинаем с entry ноды
2. Выполняем ноду (ExecutionState -> ExecutionState)
3. Ищем подходящий edge по conditions
4. Переходим к следующей ноде или завершаем
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

from apps.flows.src.constants.execution_limits import get_graph_max_iterations
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.durable_execution import (
    BreakpointHitPayload,
    EdgeActivatedPayload,
    HandoffRequestedPayload,
    InterruptRaisedPayload,
    NodeCompletedPayload,
    NodeFailedPayload,
    NodeScheduledPayload,
    NodeWriteRecordedPayload,
    SideEffectPolicy,
    SuperstepCommittedPayload,
    SuperstepStartedPayload,
    WorkflowAppendResult,
    WorkflowEventPayload,
    WorkflowEventType,
    WorkflowStateEventSpec,
    build_state_delta,
    hash_state_json,
)
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.models.flow_config import (
    CodeEdgeCondition,
    Edge,
    EdgeCondition,
    SimpleEdgeCondition,
)
from apps.flows.src.runtime.exceptions import (
    BreakpointInterrupt,
    EdgeConditionError,
    FlowInterrupt,
)
from apps.flows.src.state.cancellation import FlowCancelled, check_cancellation
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.ui_events import emit_pending_ui_events
from core.errors import (
    FlowInfiniteLoopError,
    FlowPrematureCompletionError,
    NodeCallLimitError,
)
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import HandoffInterrupt, OperatorTaskInterrupt
from core.state.mutation_policy import (
    should_skip_field_on_runtime_node_state_merge,
)
from core.tracing import get_tracer
from core.tracing.context import TraceContext, get_current_trace_context
from core.tracing.provider import is_tracing_enabled
from core.types import (
    JsonArray,
    JsonObject,
    parse_json_object,
    require_json_array,
    require_json_object,
    require_json_value,
)

from .nodes import BaseNode, create_node

logger = get_logger(__name__)

MAX_FUNCTION_CALLS = 5

class Flow:
    """
    Flow = граф нод с edges.

    Атрибуты:
        flow_id: ID flow
        name: Название
        entry: ID стартовой ноды
        nodes: Словарь нод {node_id: BaseNode}
        edges: Список edges с conditions
        variables: Резолвнутые переменные (доступны в state.variables)
        config: Полный inline FlowConfig (для передачи в state)
    """

    def __init__(
        self,
        flow_id: str,
        name: str,
        entry: str,
        nodes: dict[str, BaseNode],
        edges: Sequence[Edge | JsonObject],
        description: str = "",
        tags: list[str] | None = None,
        variables: JsonObject | None = None,
        config: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer,
    ):
        self.flow_id: str = flow_id
        self.name: str = name
        self.entry: str = entry
        self.nodes: dict[str, BaseNode] = nodes
        self.description: str = description
        self.tags: list[str] = tags or []
        self.variables: JsonObject = variables or {}
        self.config: JsonObject = config or {}  # Полный inline FlowConfig
        self.container: FlowRuntimeContainer = container
        for node in nodes.values():
            node.container = self.container

        self.edges: list[Edge] = [Edge.model_validate(edge) for edge in edges]

        # Индекс edges по from_node
        self._edges_by_from: dict[str, list[Edge]] = {}
        for edge in self.edges:
            self._edges_by_from.setdefault(edge.from_node, []).append(edge)

        self._join_required: dict[str, frozenset[str]] = self._build_join_required_predecessors()

    async def _emit_pending_ui_events(self, emitter: Emitter, state: ExecutionState) -> None:
        await emit_pending_ui_events(emitter=emitter, state=state)

    async def _checkpoint_state(
        self,
        state: ExecutionState,
        *,
        event_type: WorkflowEventType = WorkflowEventType.state_projection_committed,
        payload: WorkflowEventPayload | None = None,
    ) -> WorkflowAppendResult:
        if state.session_flow_id != self.flow_id:
            raise RuntimeError(
                f"Flow {self.flow_id!r} cannot checkpoint session for flow "
                + f"{state.session_flow_id!r}"
            )
        return await self.container.workflow_runtime.record_state_event(
            state.session_id,
            state,
            event_type=event_type,
            payload=payload,
        )

    async def _checkpoint_state_events(
        self,
        events: Sequence[WorkflowStateEventSpec],
    ) -> list[WorkflowAppendResult]:
        if not events:
            return []
        for event in events:
            state = (
                ExecutionState.model_validate(event.state)
                if isinstance(event.state, dict)
                else event.state
            )
            if state.session_flow_id != self.flow_id:
                raise RuntimeError(
                    f"Flow {self.flow_id!r} cannot checkpoint session for flow "
                    + f"{state.session_flow_id!r}"
                )
        return await self.container.workflow_runtime.record_state_events(
            events[0].state.session_id
            if isinstance(events[0].state, ExecutionState)
            else str(events[0].state["session_id"]),
            events,
        )

    @staticmethod
    def _clone_state(state: ExecutionState) -> ExecutionState:
        """Снимок ExecutionState для параллельного выполнения нод в superstep."""
        return state.model_copy(deep=True)

    @staticmethod
    def _event_sequence(event: WorkflowAppendResult | None) -> int | None:
        if event is None:
            return None
        return event.sequence

    @staticmethod
    def _event_execution_branch_id(event: WorkflowAppendResult | None) -> str | None:
        if event is None:
            return None
        return event.execution_branch_id

    @staticmethod
    def _interrupt_event(
        *,
        node_id: str,
        current_nodes: list[str],
        interrupt: FlowInterrupt,
        preserved_node_writes: list[NodeWriteRecordedPayload] | None = None,
    ) -> tuple[WorkflowEventType, WorkflowEventPayload]:
        body = interrupt.body
        preserved = preserved_node_writes or []
        if not isinstance(body, OperatorTaskInterrupt):
            return (
                WorkflowEventType.interrupt_raised,
                InterruptRaisedPayload(
                    node_id=node_id,
                    current_nodes=current_nodes,
                    preserved_node_writes=preserved,
                ),
            )
        if interrupt.correlation_id is None:
            raise RuntimeError("Operator handoff interrupt requires correlation_id")
        if body.work_item_id is None:
            raise RuntimeError("Operator handoff interrupt requires work_item_id")
        return (
            WorkflowEventType.handoff_requested,
            HandoffRequestedPayload(
                node_id=node_id,
                current_nodes=current_nodes,
                handoff_command_id=body.handoff_command_id,
                correlation_id=str(interrupt.correlation_id),
                work_item_id=body.work_item_id,
                task_title=body.task_title,
                assignee_queue=body.assignee_queue,
                handoff_mode=body.handoff_mode,
                execution_branch_id=body.execution_branch_id,
                node_schedule_sequence=body.node_schedule_sequence,
                tool_call_id=body.tool_call_id,
                preserved_node_writes=preserved,
            ),
        )

    async def _require_workflow_instance(self, state: ExecutionState) -> None:
        if state.session_flow_id != self.flow_id:
            raise RuntimeError(
                f"Flow {self.flow_id!r} requires session_id with the same flow id, "
                + f"got {state.session_id!r}"
            )
        position = await self.container.workflow_runtime.get_active_execution_position(
            state.session_id
        )
        if position is None:
            raise RuntimeError(
                f"Flow {self.flow_id!r} requires durable workflow instance "
                + f"before run: {state.session_id!r}"
            )

    @staticmethod
    def _attach_durable_node_context(
        state: ExecutionState,
        *,
        execution_branch_id: str | None,
        node_schedule_sequence: int | None,
        superstep_sequence: int | None,
    ) -> None:
        state.attach_durable_node_context(
            execution_branch_id=execution_branch_id,
            node_schedule_sequence=node_schedule_sequence,
            superstep_sequence=superstep_sequence,
        )

    @staticmethod
    def _attach_durable_edge_context(
        state: ExecutionState,
        *,
        execution_branch_id: str | None,
        edge_evaluation_sequence: int | None,
    ) -> None:
        state.attach_durable_edge_context(
            execution_branch_id=execution_branch_id,
            edge_evaluation_sequence=edge_evaluation_sequence,
        )

    async def _emit_edge_condition_error_artifact(
        self, emitter: Emitter, ece: EdgeConditionError
    ) -> None:
        await emitter.emit_edge_error(
            ece.edge_index,
            ece.from_node,
            ece.to_node,
            str(ece.original),
        )

    def _build_join_required_predecessors(self) -> dict[str, frozenset[str]]:
        """Для incoming_policy=all: множество предков по рёбрам с contributes_to_join=True."""
        acc: dict[str, set[str]] = {}
        for edge in self.edges:
            to_node = edge.to_node
            if to_node is None:
                continue
            if not edge.contributes_to_join:
                continue
            acc.setdefault(to_node, set()).add(edge.from_node)
        return {k: frozenset(v) for k, v in acc.items()}

    def _incoming_policy(self, node_id: str) -> str:
        node = self.nodes.get(node_id)
        if not node:
            return "any"
        policy = node.config.get("incoming_policy", "any")
        if policy not in ("any", "all"):
            raise ValueError(
                f"Node '{node_id}': incoming_policy must be 'any' or 'all', got {policy!r}"
            )
        return policy

    def _edge_index(self, edge: Edge) -> int:
        """Индекс ребра в `self.edges` (тот же порядок, что в конфиге flow/skill)."""
        for i, e in enumerate(self.edges):
            if e is edge:
                return i
        for i, e in enumerate(self.edges):
            if e == edge:
                return i
        raise ValueError(
            f"Flow {self.flow_id!r}: edge not in edges list: {edge!r}"
        )

    async def _iter_active_transitions_detailed(
        self, from_node: str, state: ExecutionState
    ) -> list[tuple[str, bool, int]]:
        """Исходящие активные переходы: (to_node, contributes_to_join, edge_index)."""
        edges = self._edges_by_from.get(from_node, [])
        out: list[tuple[str, bool, int]] = []
        for edge in edges:
            to_node = edge.to_node
            if to_node is None:
                continue
            edge_idx = self._edge_index(edge)
            condition = edge.condition
            try:
                if condition is None:
                    active = True
                else:
                    active = await self._evaluate_condition(
                        condition,
                        state,
                        edge_index=edge_idx,
                        from_node=from_node,
                        to_node=to_node,
                    )
            except Exception as exc:
                raise EdgeConditionError(edge_idx, from_node, to_node, exc) from exc
            if not active:
                continue
            out.append(
                (
                    to_node,
                    edge.contributes_to_join,
                    edge_idx,
                )
            )
        return out

    async def _iter_active_transitions(
        self, from_node: str, state: ExecutionState
    ) -> list[tuple[str, bool]]:
        """Исходящие переходы, для которых условие ребра выполнено: (to_node, contributes_to_join)."""
        transitions = await self._iter_active_transitions_detailed(from_node, state)
        return [(a[0], a[1]) for a in transitions]

    async def _first_active_edge_index(
        self, from_node: str, to_node: str, state: ExecutionState
    ) -> int:
        """Первое активное ребро from_node -> to_node по текущему state."""
        for edge in self._edges_by_from.get(from_node, []):
            if edge.to_node != to_node:
                continue
            edge_idx = self._edge_index(edge)
            condition = edge.condition
            try:
                if condition is None:
                    return edge_idx
                if await self._evaluate_condition(
                    condition,
                    state,
                    edge_index=edge_idx,
                    from_node=from_node,
                    to_node=to_node,
                ):
                    return edge_idx
            except Exception as exc:
                raise EdgeConditionError(edge_idx, from_node, to_node, exc) from exc
        raise ValueError(
            f"Flow {self.flow_id!r}: no active edge {from_node!r} -> {to_node!r}"
        )

    async def run(self, state: ExecutionState) -> ExecutionState:
        """
        Единственная точка входа для выполнения flow.

        Автоматически определяет режим:
        - Resume: если есть state.interrupt и state.content (ответ пользователя)
        - Handoff resume: если interrupt был HANDOFF, и дочерний вернул управление
        - Start: новый запуск с entry ноды

        Аргументы:
            state: ExecutionState

        Возвращает:
            Финальный ExecutionState
        """
        await self._require_workflow_instance(state)

        if state.interrupt and state.content:
            ir = state.interrupt
            if isinstance(ir.body, HandoffInterrupt):
                state.interrupt = None
            elif ir.correlation_id is not None and isinstance(
                ir.body, OperatorTaskInterrupt
            ):
                state.hitl_handoff_correlation_id = str(ir.correlation_id)
                state.interrupt = None
            else:
                state.interrupt = None
        elif not state.current_nodes:
            state.current_nodes = [self.entry]

        state.variables = {**self.variables, **state.variables}
        state.node_history = {}

        return await self._execute_loop(state)

    async def _execute_loop(self, state: ExecutionState) -> ExecutionState:
        """Цикл выполнения."""
        current_nodes = list(state.current_nodes) if state.current_nodes else [self.entry]
        iterations = 0
        max_graph_iterations = get_graph_max_iterations()

        emitter = Emitter(self.container.redis_client, state)

        trace_ctx = None
        if is_tracing_enabled():
            trace_ctx_data = get_current_trace_context()
            if trace_ctx_data:
                trace_ctx = TraceContext.from_dict(trace_ctx_data)

        tracer = get_tracer()
        async with tracer.flow_span(self.flow_id, self.entry, trace_ctx):
            while current_nodes:
                iterations += 1
                if iterations > max_graph_iterations:
                    raise FlowInfiniteLoopError(
                        flow_id=self.flow_id,
                        max_iterations=max_graph_iterations
                    )

                await check_cancellation(state)

                # Валидация и подготовка нод
                for node_id in current_nodes:
                    if node_id not in self.nodes:
                        raise ValueError(f"Node '{node_id}' not found in flow '{self.flow_id}'")

                    node = self.nodes[node_id]
                    node_type = self._node_type_from_config(node)
                    self._check_node_call_limit(state, node_id, node)

                    # Проверка breakpoint
                    if await self._check_breakpoint(state, node_id, node_type, emitter):
                        _ = await self._checkpoint_state(
                            state,
                            event_type=WorkflowEventType.breakpoint_hit,
                            payload=BreakpointHitPayload(
                                node_id=node_id,
                                node_type=node_type,
                            ),
                        )
                        return state

                for node_id in current_nodes:
                    node_type = self._node_type_from_config(self.nodes[node_id])
                    logger.debug(f"Flow {self.flow_id}: executing node '{node_id}' (type={node_type})")

                superstep_base_state = self._clone_state(state)
                schedule_specs = [
                    WorkflowStateEventSpec(
                        state=superstep_base_state,
                        event_type=WorkflowEventType.superstep_started,
                        payload=SuperstepStartedPayload(current_nodes=current_nodes),
                    )
                ]
                for node_id in current_nodes:
                    node_type = self._node_type_from_config(self.nodes[node_id])
                    schedule_specs.append(
                        WorkflowStateEventSpec(
                            state=superstep_base_state,
                            event_type=WorkflowEventType.node_scheduled,
                            payload=NodeScheduledPayload(
                                node_id=node_id,
                                node_type=node_type,
                                current_nodes=current_nodes,
                            ),
                        )
                    )
                scheduled_events = await self._checkpoint_state_events(schedule_specs)
                superstep_event = scheduled_events[0]
                recover_sequence = self._event_sequence(superstep_event)
                superstep_sequence = recover_sequence
                execution_branch_id = self._event_execution_branch_id(superstep_event)
                node_schedule_contexts: dict[str, tuple[str | None, int | None]] = {}
                for node_id, scheduled_event in zip(
                    current_nodes,
                    scheduled_events[1:],
                    strict=True,
                ):
                    scheduled_sequence = self._event_sequence(scheduled_event)
                    scheduled_branch_id = self._event_execution_branch_id(scheduled_event)
                    if scheduled_branch_id is not None:
                        execution_branch_id = scheduled_branch_id
                    node_schedule_contexts[node_id] = (
                        scheduled_branch_id or execution_branch_id,
                        scheduled_sequence,
                    )
                    recover_sequence = scheduled_sequence or recover_sequence

                # Выполнение всех нод текущего уровня
                async def _run(node_id: str, run_state: ExecutionState) -> ExecutionState:
                    node_type = self._node_type_from_config(self.nodes[node_id])
                    async with tracer.node_span(node_id, node_type, trace_ctx):
                        await emitter.emit_node_start(node_id, node_type)
                        try:
                            result_state = await self.nodes[node_id].execute(run_state)
                        except (FlowInterrupt, BreakpointInterrupt):
                            raise
                        except Exception as exc:
                            await emitter.emit_node_error(node_id, str(exc))
                            raise
                        preview = ""
                        if result_state.response:
                            preview = str(result_state.response)
                        elif result_state.result is not None:
                            preview = str(result_state.result)
                        await self._emit_pending_ui_events(emitter, result_state)
                        await emitter.emit_node_complete(node_id, preview)
                        return result_state

                try:
                    run_states: dict[str, ExecutionState] = {}
                    for nid in current_nodes:
                        run_states[nid] = self._clone_state(superstep_base_state)
                        branch_id, schedule_sequence = node_schedule_contexts.get(
                            nid,
                            (execution_branch_id, None),
                        )
                        self._attach_durable_node_context(
                            run_states[nid],
                            execution_branch_id=branch_id,
                            node_schedule_sequence=schedule_sequence,
                            superstep_sequence=superstep_sequence,
                        )

                    async def _run_captured(
                        node_id: str,
                        run_state: ExecutionState,
                    ) -> tuple[str, ExecutionState | None, Exception | None, ExecutionState]:
                        try:
                            return node_id, await _run(node_id, run_state), None, run_state
                        except FlowCancelled:
                            raise
                        except Exception as exc:
                            return node_id, None, exc, run_state

                    tasks = [
                        _run_captured(node_id, run_states[node_id])
                        for node_id in current_nodes
                    ]
                    outcomes = await asyncio.gather(*tasks)
                    successful_results = [
                        (node_id, result)
                        for node_id, result, exc, _run_state in outcomes
                        if exc is None and result is not None
                    ]
                    successful_node_writes: list[NodeWriteRecordedPayload] = []
                    completion_specs: list[WorkflowStateEventSpec] = []
                    for node_id, result in successful_results:
                        node_type = self._node_type_from_config(self.nodes[node_id])
                        state_delta = build_state_delta(superstep_base_state, result)
                        write_payload = NodeWriteRecordedPayload(
                            node_id=node_id,
                            node_type=node_type,
                            state_delta=state_delta,
                        )
                        successful_node_writes.append(write_payload)
                        completion_specs.append(
                            WorkflowStateEventSpec(
                                state=superstep_base_state,
                                event_type=WorkflowEventType.node_write_recorded,
                                payload=write_payload,
                            )
                        )
                        completion_specs.append(
                            WorkflowStateEventSpec(
                                state=superstep_base_state,
                                event_type=WorkflowEventType.node_completed,
                                payload=NodeCompletedPayload(
                                    node_id=node_id,
                                    node_type=node_type,
                                ),
                            )
                        )
                    completion_events = await self._checkpoint_state_events(
                        completion_specs
                    )
                    for completion_event in completion_events:
                        completion_branch_id = self._event_execution_branch_id(
                            completion_event
                        )
                        if completion_branch_id is not None:
                            execution_branch_id = completion_branch_id
                        recover_sequence = (
                            self._event_sequence(completion_event) or recover_sequence
                        )

                    result_states = [result for _, result in successful_results]

                    interrupts = [
                        (node_id, exc, run_state)
                        for node_id, _, exc, run_state in outcomes
                        if isinstance(exc, FlowInterrupt)
                    ]
                    if interrupts:
                        node_id, interrupt, interrupted_state = interrupts[0]
                        logger.info(
                            f"Flow {self.flow_id}: interrupt at '{node_id}': {interrupt.question}"
                        )
                        state = self._merge_results(
                            superstep_base_state,
                            [*result_states, interrupted_state],
                        )
                        InterruptManager.apply_interrupt(
                            state,
                            interrupt.body,
                            interrupt.tool_call,
                            interrupt.correlation_id,
                        )
                        state.current_nodes = current_nodes
                        event_type, event_payload = self._interrupt_event(
                            node_id=node_id,
                            current_nodes=current_nodes,
                            interrupt=interrupt,
                            preserved_node_writes=successful_node_writes,
                        )
                        _ = await self._checkpoint_state(
                            state,
                            event_type=event_type,
                            payload=event_payload,
                        )
                        return state

                    errors = [exc for _, _, exc, _run_state in outcomes if exc is not None]
                    if errors:
                        failed_nodes = [
                            node_id
                            for node_id, _, exc, _run_state in outcomes
                            if exc is not None
                        ]
                        _ = await self._checkpoint_state(
                            superstep_base_state,
                            event_type=WorkflowEventType.node_failed,
                            payload=NodeFailedPayload(
                                failed_nodes=failed_nodes,
                                current_nodes=current_nodes,
                                error=str(errors[0]),
                                recover_sequence=recover_sequence or 0,
                                preserved_node_writes=successful_node_writes,
                            ),
                        )
                        raise errors[0]
                    if result_states:
                        state = self._merge_results(superstep_base_state, result_states)
                    else:
                        state = self._clone_state(superstep_base_state)
                except FlowInterrupt as e:
                    node_id = current_nodes[0]
                    logger.info(f"Flow {self.flow_id}: interrupt at '{node_id}': {e.question}")
                    state = self._clone_state(superstep_base_state)
                    InterruptManager.apply_interrupt(
                        state,
                        e.body,
                        e.tool_call,
                        e.correlation_id,
                    )
                    state.current_nodes = current_nodes
                    event_type, event_payload = self._interrupt_event(
                        node_id=node_id,
                        current_nodes=current_nodes,
                        interrupt=e,
                    )
                    _ = await self._checkpoint_state(
                        state,
                        event_type=event_type,
                        payload=event_payload,
                    )
                    return state

                for node_id in current_nodes:
                    node = self.nodes[node_id]
                    node_type = self._node_type_from_config(node)
                    self._record_node_call(state, node_id, node_type)

                # Проверка interrupt
                if state.interrupt:
                    logger.info(f"Flow {self.flow_id}: interrupted")
                    state.current_nodes = current_nodes
                    _ = await self._checkpoint_state(
                        state,
                        event_type=WorkflowEventType.interrupt_raised,
                        payload=InterruptRaisedPayload(current_nodes=current_nodes),
                    )
                    return state

                try:
                    self._attach_durable_edge_context(
                        state,
                        execution_branch_id=execution_branch_id,
                        edge_evaluation_sequence=recover_sequence,
                    )
                    next_nodes, edge_activations = await self._collect_next_wave_targets(
                        current_nodes, state
                    )

                    if not next_nodes:
                        await self._raise_if_premature_completion(current_nodes, state)
                        logger.debug(f"Flow {self.flow_id}: completed")
                        state.current_nodes = []
                        _ = await self._checkpoint_state_events(
                            [
                                WorkflowStateEventSpec(
                                    state=state,
                                    event_type=WorkflowEventType.superstep_committed,
                                    payload=SuperstepCommittedPayload(
                                        completed_nodes=current_nodes,
                                        next_nodes=[],
                                    ),
                                )
                            ]
                        )
                        return state

                    transition_specs: list[WorkflowStateEventSpec] = []
                    for edge_idx, from_n, to_n in edge_activations:
                        await emitter.emit_edge_executed(edge_idx, from_n, to_n)
                        transition_specs.append(
                            WorkflowStateEventSpec(
                                state=superstep_base_state,
                                event_type=WorkflowEventType.edge_activated,
                                payload=EdgeActivatedPayload(
                                    edge_index=edge_idx,
                                    from_node=from_n,
                                    to_node=to_n,
                                ),
                            )
                        )

                    completed_nodes = list(current_nodes)
                    current_nodes = list(next_nodes)
                    state.current_nodes = current_nodes
                    transition_specs.append(
                        WorkflowStateEventSpec(
                            state=state,
                            event_type=WorkflowEventType.superstep_committed,
                            payload=SuperstepCommittedPayload(
                                completed_nodes=completed_nodes,
                                next_nodes=current_nodes,
                                edge_activations=[
                                    EdgeActivatedPayload(
                                        edge_index=edge_idx,
                                        from_node=from_n,
                                        to_node=to_n,
                                    )
                                    for edge_idx, from_n, to_n in edge_activations
                                ],
                            ),
                        )
                    )
                    _ = await self._checkpoint_state_events(transition_specs)
                except EdgeConditionError as ece:
                    await self._emit_edge_condition_error_artifact(emitter, ece)
                    raise ece.original from ece

        return state

    def _merge_results(
        self,
        original_state: ExecutionState,
        results: list[ExecutionState]
    ) -> ExecutionState:
        """Мержит результаты нод. messages - extend, остальное - кто последний."""
        merged = original_state.model_copy(deep=True)
        original_msg_count = len(original_state.messages)
        original_exc_count = len(original_state.execution_exceptions)

        for result in results:
            # messages — добавляем новые
            new_messages = result.messages[original_msg_count:]
            merged.messages.extend(new_messages)

            if result.execution_exceptions:
                new_excs = result.execution_exceptions[original_exc_count:]
                merged.execution_exceptions.extend(new_excs)

            # nested_states — мержим напрямую (без сериализации)
            if result.nested_states:
                merged.nested_states.update(result.nested_states)

            # Остальные поля — из атрибутов result, чтобы сохранять типы (например List[PromptHistoryItem])
            for field in ExecutionState.model_fields:
                if field in (
                    "messages",
                    "nested_states",
                    "join_arrived_preds",
                    "execution_exceptions",
                ):
                    continue
                if should_skip_field_on_runtime_node_state_merge(field):
                    continue
                value = result[field]
                original_value = original_state[field]
                if value == original_value:
                    continue
                if field == "variables":
                    merged.variables = {**merged.variables, **result.variables}
                    continue
                merged[field] = value

            extra = result.json_extra()
            original_extra = original_state.json_extra()
            for key, value in extra.items():
                if should_skip_field_on_runtime_node_state_merge(key):
                    continue
                if key not in original_extra or original_extra[key] != value:
                    merged[key] = value

        self._merge_join_arrived_preds(merged, results)
        return merged

    def _merge_join_arrived_preds(
        self, merged: ExecutionState, results: list[ExecutionState]
    ) -> None:
        acc: dict[str, set[str]] = {}
        for result in results:
            for target, preds in (result.join_arrived_preds or {}).items():
                acc.setdefault(target, set()).update(preds)
        merged.join_arrived_preds = {k: sorted(v) for k, v in acc.items()}

    async def _collect_next_wave_targets(
        self, completed_ids: list[str], state: ExecutionState
    ) -> tuple[set[str], list[tuple[int, str, str]]]:
        """
        Следующая волна нод: incoming_policy=all ждёт всех предков
        (рёбра с contributes_to_join); иначе — как раньше (первый пришедший).

        Второй элемент — (edge_index, from_node, to_node) для UI (подсветка рёбер).
        """
        pending: dict[str, set[str]] = {
            t: set(preds) for t, preds in (state.join_arrived_preds or {}).items()
        }
        immediate: set[str] = set()
        activations: list[tuple[int, str, str]] = []

        for pred_id in completed_ids:
            for target, contributes, edge_idx in await self._iter_active_transitions_detailed(
                pred_id, state
            ):
                policy = self._incoming_policy(target)
                if policy == "any":
                    immediate.add(target)
                    activations.append((edge_idx, pred_id, target))
                    continue
                if not contributes:
                    immediate.add(target)
                    activations.append((edge_idx, pred_id, target))
                    continue
                required = self._join_required.get(target, frozenset())
                if not required:
                    immediate.add(target)
                    activations.append((edge_idx, pred_id, target))
                    continue
                arrived = pending.setdefault(target, set())
                arrived.add(pred_id)
                if required <= arrived:
                    immediate.add(target)
                    _ = pending.pop(target, None)
                    for p in sorted(required):
                        ei = await self._first_active_edge_index(p, target, state)
                        activations.append((ei, p, target))
                    continue
                # AND-join: ждём остальных предков — edge_executed не эмитим

        state.join_arrived_preds = {k: sorted(v) for k, v in pending.items()}
        return immediate, activations

    def _node_has_structural_successor(self, node_id: str) -> bool:
        """Есть ли исходящее ребро к ноде (to не null); связи только в END (to null) не считаются."""
        for edge in self._edges_by_from.get(node_id, []):
            if edge.to_node is not None:
                return True
        return False

    def _all_structural_outgoing_edges_are_conditional(self, node_id: str) -> bool:
        """Все переходы к нодам (to не null) с условием; иначе есть безусловный выход на ноду."""
        structural: list[Edge] = [
            e
            for e in self._edges_by_from.get(node_id, [])
            if e.to_node is not None
        ]
        if not structural:
            return False
        return all(e.condition is not None for e in structural)

    async def _raise_if_premature_completion(
        self,
        completed_ids: list[str],
        state: ExecutionState,
    ) -> None:
        """
        Нельзя тихо завершить flow, если остался незакрытый AND-join
        или нода с несработавшими исходящими рёбрами к другим нодам.
        """
        pending = state.join_arrived_preds or {}
        if pending:
            details: JsonArray = []
            for target in sorted(pending.keys()):
                arrived = set(pending.get(target) or [])
                required = set(self._join_required.get(target, frozenset()))
                arrived_payload: JsonArray = [node_id for node_id in sorted(arrived)]
                required_payload: JsonArray = [node_id for node_id in sorted(required)]
                detail: JsonObject = {
                    "target": target,
                    "arrived": arrived_payload,
                    "required": required_payload,
                }
                details.append(detail)
            raise FlowPrematureCompletionError(
                self.flow_id,
                "incomplete_and_join",
                last_nodes=list(completed_ids),
                extra={"pending_joins": details},
            )

        for node_id in completed_ids:
            if not self._node_has_structural_successor(node_id):
                continue
            active = await self._iter_active_transitions(node_id, state)
            if not active:
                if self._all_structural_outgoing_edges_are_conditional(node_id):
                    reason = "no_conditional_match"
                else:
                    reason = "no_active_outgoing_edge"
                raise FlowPrematureCompletionError(
                    self.flow_id,
                    reason,
                    last_nodes=list(completed_ids),
                    extra={"stuck_at": node_id},
                )

    async def _check_breakpoint(
        self,
        state: ExecutionState,
        node_id: str,
        node_type: str,
        emitter: Emitter,
    ) -> bool:
        """
        Проверяет breakpoint и останавливает выполнение если активен.

        Аргументы:
            state: Текущий ExecutionState
            node_id: ID текущей ноды
            node_type: Тип ноды
            emitter: Emitter для публикации событий

        Возвращает:
            True если breakpoint сработал и выполнение остановлено
        """
        logger.info(f"Flow {self.flow_id}: _check_breakpoint node='{node_id}', breakpoint_hit='{state.breakpoint_hit}', breakpoints={state.breakpoints}")

        # Если мы продолжаем после breakpoint на этой же ноде - пропускаем проверку
        if state.breakpoint_hit == node_id:
            logger.debug(f"Flow {self.flow_id}: resuming after breakpoint at '{node_id}'")
            state.breakpoint_hit = None
            state.breakpoint_state = None
            return False

        # Проверяем есть ли активный breakpoint для этой ноды
        breakpoints = state.breakpoints or {}
        if not breakpoints.get(node_id):
            return False

        logger.info(f"Flow {self.flow_id}: breakpoint hit at node '{node_id}'")

        # Создаем projection snapshot
        state_snapshot = parse_json_object(
            state.model_dump_json(exclude_none=False),
            "ExecutionState.breakpoint_state",
        )

        # Публикуем событие breakpoint
        await emitter.emit_breakpoint(node_id, node_type, state_snapshot)

        # Сохраняем данные breakpoint в state
        state.breakpoint_hit = node_id
        state.breakpoint_state = state_snapshot
        state.current_nodes = [node_id]

        # Возвращаем True чтобы прервать выполнение
        return True

    def _check_node_call_limit(self, state: ExecutionState, node_id: str, node: BaseNode) -> None:
        """Проверяет лимит заходов в ноду за текущий Flow.run."""
        node_history = state.node_history.get(node_id, {})
        calls = node_history.get("calls", [])
        if not isinstance(calls, list):
            raise ValueError(f"node_history[{node_id!r}].calls must be a list")
        call_count = len(calls)
        node_type = self._node_type_from_config(node)
        configured = node.config.get("max_visits_per_run")
        if configured is None:
            if node_type == "code":
                limit = MAX_FUNCTION_CALLS
            else:
                return
        else:
            if isinstance(configured, bool) or not isinstance(configured, int):
                raise ValueError(
                    f"node.config.max_visits_per_run for '{node_id}' must be an integer"
                )
            limit = configured
        if call_count >= limit:
            raise NodeCallLimitError(node_id, limit)

    @staticmethod
    def _node_type_from_config(node: BaseNode) -> str:
        node_type = node.config.get("type")
        if not isinstance(node_type, str) or not node_type:
            raise TypeError("node.config.type must be a non-empty string")
        return node_type

    def _record_node_call(self, state: ExecutionState, node_id: str, node_type: str) -> None:
        """Записывает вызов ноды в историю."""
        if node_id not in state.node_history:
            state.node_history[node_id] = {"type": node_type, "calls": []}

        node_history = state.node_history[node_id]
        calls = node_history.get("calls")
        if not isinstance(calls, list):
            calls = []
            node_history["calls"] = calls
        calls.append(
            {
                "response": state.response,
                "validation": state.validation,
            }
        )

    async def _find_next_nodes(self, from_node: str, state: ExecutionState) -> list[str]:
        """
        Находит следующие ноды по edges.

        Возвращает ВСЕ ноды, для которых condition выполняется.
        Edge без condition - безусловный переход.
        Если несколько нод - параллельное выполнение.
        """
        seen: set[str] = set()
        ordered: list[str] = []
        for to_node, _ in await self._iter_active_transitions(from_node, state):
            if to_node not in seen:
                seen.add(to_node)
                ordered.append(to_node)
        return ordered

    async def _evaluate_condition(
        self,
        condition: EdgeCondition,
        state: ExecutionState,
        *,
        edge_index: int | None = None,
        from_node: str | None = None,
        to_node: str | None = None,
    ) -> bool:
        """
        Вычисляет условие перехода.

        Поддерживаемые форматы:
        1. SimpleEdgeCondition: {"type": "simple", "variable": "route", "operator": "==", "value": "order"}
        2. CodeEdgeCondition: {"type": "code", "language": "javascript", "code": "..."}
        """
        if isinstance(condition, SimpleEdgeCondition):
            return self._evaluate_simple_condition(condition, state)
        return await self._evaluate_code_condition(
            condition,
            state,
            edge_index=edge_index,
            from_node=from_node,
            to_node=to_node,
        )

    def _evaluate_simple_condition(self, condition: SimpleEdgeCondition, state: ExecutionState) -> bool:
        """Вычисляет простое условие: variable operator value."""
        variable = condition.variable
        op_str = condition.operator
        value = condition.value
        left = MappingResolver.get_nested_value(state, variable)

        try:
            return self._evaluate_binary_condition(left, op_str, value)
        except TypeError as e:
            message = "".join(
                (
                    f"Условие ребра: несовместимые типы для variable={variable!r} op={op_str!r} ",
                    f"left={left!r} right={value!r}",
                )
            )
            raise ValueError(message) from e

    @staticmethod
    def _evaluate_binary_condition(left: object, op_str: str, right: object) -> bool:
        if op_str == "==":
            return left == right
        if op_str == "!=":
            return left != right
        if op_str == "in":
            if isinstance(right, str):
                return str(left) in right
            if isinstance(right, (list, tuple, set, frozenset)):
                return left in right
            if isinstance(right, dict):
                return left in right
            return False

        if isinstance(left, bool) or isinstance(right, bool):
            raise TypeError("ordered comparison does not accept bool")
        if isinstance(left, (int, float)) and isinstance(right, (int, float)):
            if op_str == ">":
                return left > right
            if op_str == "<":
                return left < right
            if op_str == ">=":
                return left >= right
            if op_str == "<=":
                return left <= right
        if isinstance(left, str) and isinstance(right, str):
            if op_str == ">":
                return left > right
            if op_str == "<":
                return left < right
            if op_str == ">=":
                return left >= right
            if op_str == "<=":
                return left <= right
        raise TypeError(f"unsupported edge condition operator: {op_str!r}")

    async def _evaluate_code_condition(
        self,
        condition: CodeEdgeCondition,
        state: ExecutionState,
        *,
        edge_index: int | None = None,
        from_node: str | None = None,
        to_node: str | None = None,
    ) -> bool:
        """
        Вычисляет code-condition через isolated remote code runner.

        Контракт тот же, что у code_node/tool: entrypoint `(args, state)`.
        Если entrypoint не задан, runner вызывает первую функцию в source.
        Condition исполняется на копии state, поэтому переходы не мутируют runtime state.
        """
        code = condition.code
        language = condition.language
        entrypoint = condition.entrypoint
        input_payload = require_json_object(
            {
                "flow_id": self.flow_id,
                "edge_index": edge_index,
                "from_node": from_node,
                "to_node": to_node,
                "language": language,
                "entrypoint": entrypoint,
                "code": code,
                "state_hash": self._state_hash_for_activity(state),
            },
            "edge.code_condition.activity_input",
        )
        activity_id = await self._durable_edge_activity_id(
            state=state,
            edge_index=edge_index,
            from_node=from_node,
            to_node=to_node,
            input_payload=input_payload,
        )
        runtime = self.container.workflow_runtime
        completed = await runtime.record_activity_scheduled(
            session_id=state.session_id,
            activity_id=activity_id,
            activity_type="code_condition",
            input_payload=input_payload,
            node_id=from_node,
            idempotency_key=activity_id,
            side_effect_policy=SideEffectPolicy.idempotent,
        )
        if completed is not None:
            result = require_json_value(
                completed.get("result"),
                "edge.code_condition.result",
            )
            return bool(result)

        started = await runtime.record_activity_started(activity_id=activity_id)
        if not started:
            raise RuntimeError(f"Failed to mark code condition activity as started: {activity_id!r}")

        condition_state = state.model_copy(deep=True)
        runner = self.container.get_code_runner(language=language)
        try:
            result = await runner.execute_tool(code, {}, condition_state, entrypoint=entrypoint)
        except Exception as exc:
            completed_failed = await runtime.record_activity_completed(
                activity_id=activity_id,
                error=str(exc),
            )
            if not completed_failed:
                raise RuntimeError(
                    f"Failed to mark code condition activity as failed: {activity_id!r}"
                ) from exc
            raise ValueError(
                f"Code-условие ребра: ошибка выполнения language={language!r}: {exc}"
            ) from exc
        condition_result = bool(result)
        completed_ok = await runtime.record_activity_completed(
            activity_id=activity_id,
            result_json={"result": condition_result},
        )
        if not completed_ok:
            raise RuntimeError(
                f"Failed to mark code condition activity as completed: {activity_id!r}"
            )
        return condition_result

    async def _durable_edge_activity_id(
        self,
        *,
        state: ExecutionState,
        edge_index: int | None,
        from_node: str | None,
        to_node: str | None,
        input_payload: JsonObject,
    ) -> str:
        input_hash = hash_state_json(input_payload)
        execution_branch_id = state.durable_edge_execution_branch_id
        evaluation_sequence = state.durable_edge_evaluation_sequence

        if execution_branch_id is None or evaluation_sequence is None:
            raise RuntimeError("Code edge condition requires attached durable edge context")
        if edge_index is None or from_node is None or to_node is None:
            raise RuntimeError("Code edge condition requires explicit edge scope")

        sequence_part = f"evaluation:{evaluation_sequence}"
        edge_part = edge_index
        from_part = from_node
        to_part = to_node
        return (
            f"{state.session_id}:{execution_branch_id}:edge:{edge_part}:"
            + f"{from_part}:{to_part}:code_condition:{sequence_part}:input:{input_hash}"
        )

    @staticmethod
    def _state_hash_for_activity(state: ExecutionState) -> str:
        payload = require_json_object(
            state.model_dump(mode="json", exclude_none=False),
            "activity.state",
        )
        _ = payload.pop("flow_config", None)
        return hash_state_json(payload)

    @classmethod
    async def from_config(
        cls,
        config: Mapping[str, object],
        variables: JsonObject | None = None,
        *,
        container: FlowRuntimeContainer,
    ) -> "Flow":
        """
        Создаёт flow из FlowConfig.

        Аргументы:
            config: FlowConfig (model_dump() или dict)
            variables: Опционально - pre-resolved переменные выполнения.

        Возвращает:
            Экземпляр Flow
        """
        config_json = require_json_object(config, "flow_config")

        raw_flow_id = config_json.get("flow_id")
        if not isinstance(raw_flow_id, str) or not raw_flow_id.strip():
            raise ValueError("Flow.from_config requires non-empty flow_id")

        nodes: dict[str, BaseNode] = {}
        raw_nodes_config = config_json.get("nodes")
        nodes_config = (
            require_json_object(raw_nodes_config, "flow_config.nodes")
            if raw_nodes_config is not None
            else {}
        )
        for node_id, node_config in nodes_config.items():
            nodes[node_id] = await create_node(
                node_id,
                require_json_object(node_config, f"flow_config.nodes.{node_id}"),
                container=container,
            )

        # variables: pre-resolved runtime payload > persisted resolved_variables > authored variables из конфига (по приоритету).
        raw_variables = variables
        if raw_variables is None:
            raw_variables = config_json.get("resolved_variables")
        if raw_variables is None:
            raw_variables = config_json.get("variables")
        resolved_variables = (
            require_json_object(raw_variables, "flow_config.variables")
            if raw_variables is not None
            else {}
        )

        raw_entry = config_json.get("entry")
        if not isinstance(raw_entry, str) or not raw_entry.strip():
            raise ValueError("Flow.from_config requires non-empty entry")

        raw_name = config_json.get("name")
        if not isinstance(raw_name, str):
            raise ValueError("Flow.from_config name must be a string")

        raw_description = config_json.get("description", "")
        if raw_description is None:
            raw_description = ""
        if not isinstance(raw_description, str):
            raise ValueError("Flow.from_config description must be a string")

        raw_tags = config_json.get("tags")
        tags: list[str] = []
        if raw_tags is not None:
            for index, item in enumerate(require_json_array(raw_tags, "flow_config.tags")):
                if not isinstance(item, str):
                    raise ValueError(f"flow_config.tags[{index}] must be a string")
                tags.append(item)

        raw_edges = config_json.get("edges")
        edges: list[Edge] = []
        if raw_edges is not None:
            edges = [
                Edge.model_validate(
                    require_json_object(item, f"flow_config.edges[{index}]")
                )
                for index, item in enumerate(require_json_array(raw_edges, "flow_config.edges"))
            ]

        return cls(
            flow_id=raw_flow_id,
            name=raw_name,
            entry=raw_entry,
            nodes=nodes,
            edges=edges,
            description=raw_description,
            tags=tags,
            variables=resolved_variables,
            config=config_json,
            container=container,
        )
