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
import re
from typing import Any

from apps.flows.src.constants.execution_limits import get_graph_max_iterations
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.mapping import MappingResolver
from apps.flows.src.runtime.exceptions import (
    BreakpointInterrupt,
    EdgeConditionError,
    FlowInterrupt,
)
from apps.flows.src.state.cancellation import FlowCancelled, check_cancellation
from apps.flows.src.state.interrupt_manager import InterruptManager
from apps.flows.src.streaming import Emitter
from apps.flows.src.streaming.memory import InMemoryEmitter
from apps.flows.src.streaming.ui_events import emit_pending_ui_events
from core.errors import (
    FlowInfiniteLoopError,
    FlowPrematureCompletionError,
    NodeCallLimitError,
)
from core.logging import get_logger
from core.state import ExecutionState
from core.state.interrupt import OperatorTaskInterrupt
from core.state.mutation_policy import should_skip_field_on_user_returned_state_copy
from core.tracing import get_tracer
from core.tracing.context import TraceContext, get_current_trace_context
from core.tracing.provider import is_tracing_enabled
from core.types import JsonArray, JsonObject

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
        edges: list[dict[str, Any] | Any],
        description: str = "",
        tags: list[str] | None = None,
        variables: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
        container: FlowRuntimeContainer | None = None,
    ):
        self.flow_id = flow_id
        self.name = name
        self.entry = entry
        self.nodes = nodes
        self.description = description
        self.tags = tags or []
        self.variables = variables or {}
        self.config = config or {}  # Полный inline FlowConfig
        self.container = container
        if self.container is not None:
            for node in nodes.values():
                if node.container is None:
                    node.container = self.container

        # Нормализуем edges в единый формат (список словарей)
        self.edges = self._normalize_edges(edges)

        # Индекс edges по from_node
        self._edges_by_from: dict[str, list[dict[str, Any]]] = {}
        for edge in self.edges:
            from_node = edge["from"]
            if from_node not in self._edges_by_from:
                self._edges_by_from[from_node] = []
            self._edges_by_from[from_node].append(edge)

        self._join_required = self._build_join_required_predecessors()

    async def _emit_pending_ui_events(self, emitter: Emitter | InMemoryEmitter, state: ExecutionState) -> None:
        await emit_pending_ui_events(emitter=emitter, state=state)

    async def _checkpoint_state(self, state: ExecutionState) -> None:
        if self.container is None:
            return
        if getattr(state, "_skip_hot_state_checkpoint", False):
            return
        if state.session_flow_id != self.flow_id:
            return
        await self.container.state_manager.save_state(state.session_id, state)

    async def _emit_edge_condition_error_artifact(
        self, emitter: Emitter | InMemoryEmitter, ece: EdgeConditionError
    ) -> None:
        await emitter.emit_edge_error(
            ece.edge_index,
            ece.from_node,
            ece.to_node,
            str(ece.original),
        )

    def _normalize_edges(self, edges: list[Any]) -> list[dict[str, Any]]:
        """Нормализует edges в list of dicts."""
        result = []
        for edge in edges:
            if isinstance(edge, dict):
                cj = edge.get("contributes_to_join")
                contributes = True if cj is None else bool(cj)
                result.append(
                    {
                        "from": edge.get("from"),
                        "to": edge.get("to"),
                        "condition": edge.get("condition"),
                        "contributes_to_join": contributes,
                    }
                )
            else:
                contributes = bool(getattr(edge, "contributes_to_join", True))
                result.append(
                    {
                        "from": edge.from_node,
                        "to": edge.to_node,
                        "condition": edge.condition,
                        "contributes_to_join": contributes,
                    }
                )
        return result

    def _build_join_required_predecessors(self) -> dict[str, frozenset[str]]:
        """Для incoming_policy=all: множество предков по рёбрам с contributes_to_join=True."""
        acc: dict[str, set[str]] = {}
        for edge in self.edges:
            to_n = edge.get("to")
            from_n = edge.get("from")
            if not to_n or not from_n:
                continue
            if not edge.get("contributes_to_join", True):
                continue
            acc.setdefault(to_n, set()).add(from_n)
        return {k: frozenset(v) for k, v in acc.items()}

    @staticmethod
    def _edge_contributes_to_join(edge: dict[str, Any]) -> bool:
        return bool(edge.get("contributes_to_join", True))

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

    def _edge_index(self, edge: dict[str, Any]) -> int:
        """Индекс ребра в `self.edges` (тот же порядок, что в конфиге flow/skill)."""
        for i, e in enumerate(self.edges):
            if e is edge:
                return i
        for i, e in enumerate(self.edges):
            if (
                e.get("from") == edge.get("from")
                and e.get("to") == edge.get("to")
                and e.get("condition") == edge.get("condition")
                and e.get("contributes_to_join") == edge.get("contributes_to_join")
            ):
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
            to_node = edge.get("to")
            if to_node is None:
                continue
            edge_idx = self._edge_index(edge)
            condition = edge.get("condition")
            try:
                if condition is None:
                    active = True
                else:
                    active = await self._evaluate_condition(condition, state)
            except Exception as exc:
                raise EdgeConditionError(edge_idx, from_node, to_node, exc) from exc
            if not active:
                continue
            out.append(
                (
                    to_node,
                    self._edge_contributes_to_join(edge),
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
            if edge.get("to") != to_node:
                continue
            edge_idx = self._edge_index(edge)
            condition = edge.get("condition")
            try:
                if condition is None:
                    return edge_idx
                if await self._evaluate_condition(condition, state):
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
        - Start: новый запуск с entry ноды

        Args:
            state: ExecutionState

        Returns:
            Финальный ExecutionState
        """
        if state.interrupt and state.content:
            # Resume: есть interrupt и новый контент (ответ пользователя)
            logger.info(f"Flow {self.flow_id}: resume with answer='{state.content[:50]}...'")
            ir = state.interrupt
            if ir.correlation_id is not None and isinstance(
                ir.body, OperatorTaskInterrupt
            ):
                state.hitl_handoff_correlation_id = str(ir.correlation_id)
            state.interrupt = None
        elif not state.current_nodes:
            # Start: новый запуск
            state.current_nodes = [self.entry]

        state.variables = {**self.variables, **state.variables}
        state.node_history = {}

        return await self._execute_loop(state)

    async def _execute_loop(self, state: ExecutionState) -> ExecutionState:
        """Цикл выполнения."""
        current_nodes = list(state.current_nodes) if state.current_nodes else [self.entry]
        iterations = 0
        max_graph_iterations = get_graph_max_iterations()

        emitter: Emitter | InMemoryEmitter
        if self.container is None:
            emitter = InMemoryEmitter(state)
        else:
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
                        await self._checkpoint_state(state)
                        return state

                for node_id in current_nodes:
                    node_type = self._node_type_from_config(self.nodes[node_id])
                    logger.debug(f"Flow {self.flow_id}: executing node '{node_id}' (type={node_type})")

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
                    if len(current_nodes) > 1:
                        for nid in current_nodes:
                            run_states[nid] = ExecutionState.model_validate(
                                state.model_dump(exclude_none=False)
                            )
                    else:
                        for nid in current_nodes:
                            run_states[nid] = state

                    async def _run_captured(
                        node_id: str,
                        run_state: ExecutionState,
                    ) -> tuple[str, ExecutionState | None, Exception | None]:
                        try:
                            return node_id, await _run(node_id, run_state), None
                        except FlowCancelled:
                            raise
                        except Exception as exc:
                            return node_id, None, exc

                    tasks = [
                        _run_captured(node_id, run_states[node_id])
                        for node_id in current_nodes
                    ]
                    outcomes = await asyncio.gather(*tasks)
                    results = [
                        result
                        for _, result, exc in outcomes
                        if exc is None and result is not None
                    ]
                    if results:
                        state = self._merge_results(state, results)

                    interrupts = [
                        (node_id, exc)
                        for node_id, _, exc in outcomes
                        if isinstance(exc, FlowInterrupt)
                    ]
                    if interrupts:
                        node_id, interrupt = interrupts[0]
                        logger.info(
                            f"Flow {self.flow_id}: interrupt at '{node_id}': {interrupt.question}"
                        )
                        InterruptManager.apply_interrupt(
                            state,
                            interrupt.body,
                            interrupt.tool_call,
                            getattr(interrupt, "correlation_id", None),
                        )
                        state.current_nodes = current_nodes
                        await self._checkpoint_state(state)
                        return state

                    errors = [exc for _, _, exc in outcomes if exc is not None]
                    if errors:
                        raise errors[0]
                except FlowInterrupt as e:
                    node_id = current_nodes[0]
                    logger.info(f"Flow {self.flow_id}: interrupt at '{node_id}': {e.question}")
                    InterruptManager.apply_interrupt(
                        state,
                        e.body,
                        e.tool_call,
                        getattr(e, "correlation_id", None),
                    )
                    state.current_nodes = current_nodes
                    await self._checkpoint_state(state)
                    return state

                for node_id in current_nodes:
                    node = self.nodes[node_id]
                    node_type = self._node_type_from_config(node)
                    self._record_node_call(state, node_id, node_type)

                # Проверка interrupt
                if state.interrupt:
                    logger.info(f"Flow {self.flow_id}: interrupted")
                    state.current_nodes = current_nodes
                    await self._checkpoint_state(state)
                    return state

                try:
                    next_nodes, edge_activations = await self._collect_next_wave_targets(
                        current_nodes, state
                    )

                    if not next_nodes:
                        await self._raise_if_premature_completion(current_nodes, state)
                        logger.debug(f"Flow {self.flow_id}: completed")
                        state.current_nodes = []
                        await self._checkpoint_state(state)
                        return state

                    for edge_idx, from_n, to_n in edge_activations:
                        await emitter.emit_edge_executed(edge_idx, from_n, to_n)

                    current_nodes = list(next_nodes)
                    state.current_nodes = current_nodes
                    await self._checkpoint_state(state)
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
            # messages - добавляем новые
            new_messages = result.messages[original_msg_count:]
            merged.messages.extend(new_messages)

            if result.execution_exceptions:
                new_excs = result.execution_exceptions[original_exc_count:]
                merged.execution_exceptions.extend(new_excs)

            # nested_states - мержим напрямую (без сериализации)
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
                if should_skip_field_on_user_returned_state_copy(field):
                    continue
                value = getattr(result, field)
                if value is not None:
                    if isinstance(value, list):
                        setattr(merged, field, list(value))
                    else:
                        setattr(merged, field, value)

            extra = getattr(result, "__pydantic_extra__", None) or {}
            for key, value in extra.items():
                if should_skip_field_on_user_returned_state_copy(key):
                    continue
                setattr(merged, key, value)

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
                    pending.pop(target, None)
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
            if edge.get("to") is not None:
                return True
        return False

    def _all_structural_outgoing_edges_are_conditional(self, node_id: str) -> bool:
        """Все переходы к нодам (to не null) с условием; иначе есть безусловный выход на ноду."""
        structural: list[dict[str, Any]] = [
            e
            for e in self._edges_by_from.get(node_id, [])
            if e.get("to") is not None
        ]
        if not structural:
            return False
        return all(e.get("condition") is not None for e in structural)

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
        emitter: Emitter | InMemoryEmitter,
    ) -> bool:
        """
        Проверяет breakpoint и останавливает выполнение если активен.

        Args:
            state: Текущий ExecutionState
            node_id: ID текущей ноды
            node_type: Тип ноды
            emitter: Emitter для публикации событий

        Returns:
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

        # Создаем snapshot state
        state_snapshot = state.model_dump(exclude_none=False)

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
        node_type = node.config.get("type", "function")
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

    async def _evaluate_condition(self, condition: Any, state: ExecutionState) -> bool:
        """
        Вычисляет условие перехода.

        Поддерживаемые форматы:
        1. Объект с type='simple': {"type": "simple", "variable": "route", "operator": "==", "value": "order"}
        2. Объект с type='code': {"type": "code", "language": "javascript", "code": "..."}
        3. Строка: "field == value", "field != value", и т.д.
        """
        if isinstance(condition, dict):
            return await self._evaluate_condition_object(condition, state)

        return self._evaluate_condition_string(str(condition), state)

    async def _evaluate_condition_object(self, condition: dict[str, Any], state: ExecutionState) -> bool:
        """Вычисляет условие в новом объектном формате."""
        condition_type = condition.get("type")

        if condition_type == "simple":
            return self._evaluate_simple_condition(condition, state)
        if condition_type == "code":
            return await self._evaluate_code_condition(condition, state)

        raise ValueError(
            f"Неизвестный type условия ребра: {condition_type!r}, ожидаются 'simple' или 'code'"
        )

    def _evaluate_simple_condition(self, condition: dict[str, Any], state: ExecutionState) -> bool:
        """Вычисляет простое условие: variable operator value."""
        variable = condition.get("variable", "")
        op_str = condition.get("operator", "==")
        value = condition.get("value", "")
        left = MappingResolver.get_nested_value(state, variable)
        right = self._parse_value(str(value)) if not isinstance(value, (bool, int, float)) else value

        try:
            return self._evaluate_binary_condition(left, str(op_str), right)
        except TypeError as e:
            raise ValueError(
                f"Условие ребра: несовместимые типы для variable={variable!r} "
                f"op={op_str!r} left={left!r} right={right!r}"
            ) from e

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

    async def _evaluate_code_condition(self, condition: dict[str, Any], state: ExecutionState) -> bool:
        """
        Вычисляет code-condition через isolated remote code runner.

        Контракт тот же, что у code_node/tool: entrypoint `(args, state)`.
        Если entrypoint не задан, runner вызывает первую функцию в source.
        Condition исполняется на копии state, поэтому переходы не мутируют runtime state.
        """
        if self.container is None:
            raise RuntimeError("Code edge condition requires FlowContainer")
        code = condition.get("code")
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Code-условие ребра: требуется непустой code")
        language = condition.get("language", "python")
        if not isinstance(language, str) or not language.strip():
            raise ValueError("Code-условие ребра: language должен быть непустой строкой")
        raw_entrypoint = condition.get("entrypoint")
        entrypoint = raw_entrypoint.strip() if isinstance(raw_entrypoint, str) and raw_entrypoint.strip() else None
        condition_state = ExecutionState.model_validate(state.model_dump(exclude_none=False))
        runner = self.container.get_code_runner(language=language)
        try:
            result = await runner.execute_tool(code, {}, condition_state, entrypoint=entrypoint)
        except Exception as exc:
            raise ValueError(
                f"Code-условие ребра: ошибка выполнения language={language!r}: {exc}"
            ) from exc
        return bool(result)

    def _evaluate_condition_string(self, condition: str, state: ExecutionState) -> bool:
        """Вычисляет условие в legacy строковом формате."""
        # Двухсимвольные операторы раньше односимвольных: иначе "count <= 3" матчится как "count" > "= 3".
        patterns = [
            (r"(.+?)\s*==\s*(.+)", "=="),
            (r"(.+?)\s*!=\s*(.+)", "!="),
            (r"(.+?)\s*>=\s*(.+)", ">="),
            (r"(.+?)\s*<=\s*(.+)", "<="),
            (r"(.+?)\s*>\s*(.+)", ">"),
            (r"(.+?)\s*<\s*(.+)", "<"),
        ]

        for pattern, op_str in patterns:
            match = re.match(pattern, condition.strip())
            if match:
                left_path = match.group(1).strip()
                right_value = match.group(2).strip()

                left = MappingResolver.get_nested_value(state, left_path)
                right = self._parse_value(right_value)

                try:
                    return self._evaluate_binary_condition(left, op_str, right)
                except TypeError as e:
                    raise ValueError(
                        f"Строковое условие ребра: несовместимые типы "
                        f"left_path={left_path!r} right={right_value!r} left={left!r} right={right!r}"
                    ) from e

        value = MappingResolver.get_nested_value(state, condition.strip())
        return bool(value)

    def _parse_value(self, value: str) -> Any:
        """Парсит значение из строки."""
        value = value.strip()

        # Boolean
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False

        # None
        if value.lower() == "null" or value.lower() == "none":
            return None

        # String в кавычках
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]

        if re.fullmatch(r"-?\d+", value):
            return int(value)
        if re.fullmatch(r"-?\d+\.\d+", value):
            return float(value)

        return value

    @classmethod
    async def from_config(
        cls,
        config: dict[str, Any],
        variables: dict[str, Any] | None = None,
        *,
        container: FlowRuntimeContainer | None = None,
    ) -> "Flow":
        """
        Создаёт flow из FlowConfig.

        Args:
            config: FlowConfig (model_dump() или dict)
            variables: Опционально - переопределение variables (для обратной совместимости)

        Returns:
            Экземпляр Flow
        """
        # flow_id может быть в "flow_id" или "id"
        flow_id = config.get("flow_id") or config.get("id")

        nodes = {}
        nodes_config = config.get("nodes", {})
        for node_id, node_config in nodes_config.items():
            nodes[node_id] = await create_node(node_id, node_config, container=container)

        # variables: параметр > config["resolved_variables"] > config["variables"]
        resolved_variables = (
            variables
            or config.get("resolved_variables")
            or config.get("variables", {})
        )

        raw_flow_id = flow_id
        if not isinstance(raw_flow_id, str) or not raw_flow_id.strip():
            raise ValueError("Flow.from_config requires non-empty flow_id")

        return cls(
            flow_id=raw_flow_id,
            name=config.get("name", ""),
            entry=config.get("entry", "main"),
            nodes=nodes,
            edges=config.get("edges", []),
            description=config.get("description", ""),
            tags=config.get("tags", []),
            variables=resolved_variables,
            config=config,
            container=container,
        )
