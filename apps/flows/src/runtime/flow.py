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
import operator
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from opentelemetry import trace

from apps.flows.src.runtime.exceptions import FlowInterrupt, BreakpointInterrupt, NodeCallLimitError
from apps.flows.src.container import get_container
from apps.flows.src.state.cancellation import check_cancellation
from apps.flows.src.state.interrupt_manager import InterruptManager
from core.state import ExecutionState
from core.state.interrupt import OperatorTaskInterrupt
from apps.flows.src.streaming import Emitter
from apps.flows.src.mapping import MappingResolver
from core.logging import get_logger
from core.tracing import get_tracer
from core.tracing.context import TraceContext, get_current_trace_context
from core.tracing.provider import is_tracing_enabled
from core.errors import (
    FlowInfiniteLoopError,
    FlowPrematureCompletionError,
    NodeCallLimitError,
)

from .nodes import BaseNode, create_node

logger = get_logger(__name__)

MAX_ITERATIONS = 100
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
        nodes: Dict[str, BaseNode],
        edges: List[Union[Dict[str, Any], Any]],
        description: str = "",
        tags: Optional[List[str]] = None,
        variables: Optional[Dict[str, Any]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.flow_id = flow_id
        self.name = name
        self.entry = entry
        self.nodes = nodes
        self.description = description
        self.tags = tags or []
        self.variables = variables or {}
        self.config = config or {}  # Полный inline FlowConfig

        # Нормализуем edges в единый формат (список словарей)
        self.edges = self._normalize_edges(edges)

        # Индекс edges по from_node
        self._edges_by_from: Dict[str, List[Dict[str, Any]]] = {}
        for edge in self.edges:
            from_node = edge["from"]
            if from_node not in self._edges_by_from:
                self._edges_by_from[from_node] = []
            self._edges_by_from[from_node].append(edge)

        self._join_required = self._build_join_required_predecessors()

    def _normalize_edges(self, edges: List[Any]) -> List[Dict[str, Any]]:
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

    def _build_join_required_predecessors(self) -> Dict[str, frozenset[str]]:
        """Для incoming_policy=all: множество предков по рёбрам с contributes_to_join=True."""
        acc: Dict[str, Set[str]] = {}
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
    def _edge_contributes_to_join(edge: Dict[str, Any]) -> bool:
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

    def _iter_active_transitions(
        self, from_node: str, state: ExecutionState
    ) -> List[Tuple[str, bool]]:
        """Исходящие переходы, для которых условие ребра выполнено: (to_node, contributes_to_join)."""
        edges = self._edges_by_from.get(from_node, [])
        out: List[Tuple[str, bool]] = []
        for edge in edges:
            to_node = edge.get("to")
            if to_node is None:
                continue
            condition = edge.get("condition")
            if condition is None:
                ok = True
            elif self._evaluate_condition(condition, state):
                ok = True
            else:
                continue
            out.append((to_node, self._edge_contributes_to_join(edge)))
        return out

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

        return await self._execute_loop(state)

    async def _execute_loop(self, state: ExecutionState) -> ExecutionState:
        """Цикл выполнения."""
        current_nodes = list(state.current_nodes) if state.current_nodes else [self.entry]
        iterations = 0

        container = get_container()
        emitter = Emitter(container.redis_client, state)

        trace_ctx = None
        if is_tracing_enabled():
            trace_ctx_data = get_current_trace_context()
            if trace_ctx_data:
                trace_ctx = TraceContext.from_dict(trace_ctx_data)

        tracer = get_tracer()
        async with tracer.flow_span(self.flow_id, self.entry, trace_ctx):
            while current_nodes:
                iterations += 1
                if iterations > MAX_ITERATIONS:
                    raise FlowInfiniteLoopError(
                        flow_id=self.flow_id,
                        max_iterations=MAX_ITERATIONS
                    )

                await check_cancellation()

                # Валидация и подготовка нод
                for node_id in current_nodes:
                    if node_id not in self.nodes:
                        raise ValueError(f"Node '{node_id}' not found in flow '{self.flow_id}'")
                    
                    node = self.nodes[node_id]
                    node_type = node.config.get("type", "function")
                    self._check_node_call_limit(state, node_id, node_type)
                    
                    # Проверка breakpoint
                    if await self._check_breakpoint(state, node_id, node_type, emitter):
                        return state

                for node_id in current_nodes:
                    node_type = self.nodes[node_id].config.get("type", "function")
                    logger.debug(f"Flow {self.flow_id}: executing node '{node_id}' (type={node_type})")

                # Выполнение всех нод текущего уровня
                async def _run(node_id: str, run_state: ExecutionState) -> ExecutionState:
                    node_type = self.nodes[node_id].config.get("type", "function")
                    async with tracer.node_span(node_id, node_type, trace_ctx):
                        await emitter.emit_node_start(node_id, node_type)
                        try:
                            result_state = await self.nodes[node_id].run.kiq(run_state)
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
                        await emitter.emit_node_complete(node_id, preview)
                        return result_state

                try:
                    run_states: Dict[str, ExecutionState] = {}
                    if len(current_nodes) > 1:
                        for nid in current_nodes:
                            run_states[nid] = ExecutionState.model_validate(
                                state.model_dump(exclude_none=False)
                            )
                    else:
                        for nid in current_nodes:
                            run_states[nid] = state

                    tasks = [
                        _run(node_id, run_states[node_id])
                        for node_id in current_nodes
                    ]
                    results = await asyncio.gather(*tasks)
                    state = self._merge_results(state, results)
                except FlowInterrupt as e:
                    node_id = current_nodes[0]  # interrupt от первой ноды
                    logger.info(f"Flow {self.flow_id}: interrupt at '{node_id}': {e.question}")
                    InterruptManager.apply_interrupt(
                        state,
                        e.body,
                        e.tool_call,
                        getattr(e, "correlation_id", None),
                    )
                    state.current_nodes = current_nodes
                    return state

                for node_id in current_nodes:
                    node = self.nodes[node_id]
                    node_type = node.config.get("type", "function")
                    self._record_node_call(state, node_id, node_type)

                # Проверка interrupt
                if state.interrupt:
                    logger.info(f"Flow {self.flow_id}: interrupted")
                    state.current_nodes = current_nodes
                    return state

                next_nodes = self._collect_next_wave_targets(current_nodes, state)

                if not next_nodes:
                    self._raise_if_premature_completion(current_nodes, state)
                    logger.debug(f"Flow {self.flow_id}: completed")
                    state.current_nodes = []
                    return state

                current_nodes = list(next_nodes)
        
        return state

    def _merge_results(
        self,
        original_state: ExecutionState,
        results: List[ExecutionState]
    ) -> ExecutionState:
        """Мержит результаты нод. messages - extend, остальное - кто последний."""
        merged = original_state.model_copy(deep=True)
        original_msg_count = len(original_state.messages)

        for result in results:
            # messages - добавляем новые
            new_messages = result.messages[original_msg_count:]
            merged.messages.extend(new_messages)

            # nested_states - мержим напрямую (без сериализации)
            if result.nested_states:
                merged.nested_states.update(result.nested_states)

            # Остальные поля — из атрибутов result, чтобы сохранять типы (например List[PromptHistoryItem])
            for field in ExecutionState.model_fields:
                if field in ("messages", "nested_states", "join_arrived_preds"):
                    continue
                value = getattr(result, field)
                if value is not None:
                    if isinstance(value, list):
                        setattr(merged, field, list(value))
                    else:
                        setattr(merged, field, value)

            extra = getattr(result, "__pydantic_extra__", None) or {}
            for key, value in extra.items():
                setattr(merged, key, value)

        self._merge_join_arrived_preds(merged, results)
        return merged

    def _merge_join_arrived_preds(
        self, merged: ExecutionState, results: List[ExecutionState]
    ) -> None:
        acc: Dict[str, Set[str]] = {}
        for result in results:
            for target, preds in (result.join_arrived_preds or {}).items():
                acc.setdefault(target, set()).update(preds)
        merged.join_arrived_preds = {k: sorted(v) for k, v in acc.items()}

    def _collect_next_wave_targets(
        self, completed_ids: List[str], state: ExecutionState
    ) -> Set[str]:
        """
        Следующая волна нод: incoming_policy=all ждёт всех предков
        (рёбра с contributes_to_join); иначе — как раньше (первый пришедший).
        """
        pending: Dict[str, Set[str]] = {
            t: set(preds) for t, preds in (state.join_arrived_preds or {}).items()
        }
        immediate: Set[str] = set()

        for pred_id in completed_ids:
            for target, contributes in self._iter_active_transitions(pred_id, state):
                policy = self._incoming_policy(target)
                if policy == "any":
                    immediate.add(target)
                    continue
                if not contributes:
                    immediate.add(target)
                    continue
                required = self._join_required.get(target, frozenset())
                if not required:
                    immediate.add(target)
                    continue
                arrived = pending.setdefault(target, set())
                arrived.add(pred_id)
                if required <= arrived:
                    immediate.add(target)
                    pending.pop(target, None)

        state.join_arrived_preds = {k: sorted(v) for k, v in pending.items()}
        return immediate

    def _node_has_structural_successor(self, node_id: str) -> bool:
        """Есть ли исходящее ребро к ноде (to не null); связи только в END (to null) не считаются."""
        for edge in self._edges_by_from.get(node_id, []):
            if edge.get("to") is not None:
                return True
        return False

    def _all_structural_outgoing_edges_are_conditional(self, node_id: str) -> bool:
        """Все переходы к нодам (to не null) с условием; иначе есть безусловный выход на ноду."""
        structural: List[Dict[str, Any]] = [
            e
            for e in self._edges_by_from.get(node_id, [])
            if e.get("to") is not None
        ]
        if not structural:
            return False
        return all(e.get("condition") is not None for e in structural)

    def _raise_if_premature_completion(
        self,
        completed_ids: List[str],
        state: ExecutionState,
    ) -> None:
        """
        Нельзя тихо завершить flow, если остался незакрытый AND-join
        или нода с несработавшими исходящими рёбрами к другим нодам.
        """
        pending = state.join_arrived_preds or {}
        if pending:
            details: List[Dict[str, Any]] = []
            for target in sorted(pending.keys()):
                arrived = set(pending.get(target) or [])
                required = set(self._join_required.get(target, frozenset()))
                details.append(
                    {
                        "target": target,
                        "arrived": sorted(arrived),
                        "required": sorted(required),
                    }
                )
            raise FlowPrematureCompletionError(
                self.flow_id,
                "incomplete_and_join",
                last_nodes=list(completed_ids),
                extra={"pending_joins": details},
            )

        for node_id in completed_ids:
            if not self._node_has_structural_successor(node_id):
                continue
            active = self._iter_active_transitions(node_id, state)
            if not active:
                if self._all_structural_outgoing_edges_are_conditional(node_id):
                    continue
                raise FlowPrematureCompletionError(
                    self.flow_id,
                    "no_active_outgoing_edge",
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

    def _check_node_call_limit(self, state: ExecutionState, node_id: str, node_type: str) -> None:
        """Проверяет лимит вызовов ноды."""
        node_history = state.node_history.get(node_id, {})
        call_count = len(node_history.get("calls", []))

        if node_type == "code" and call_count >= MAX_FUNCTION_CALLS:
            raise NodeCallLimitError(
                f"Node '{node_id}' (type={node_type}): превышен лимит {MAX_FUNCTION_CALLS} вызовов",
                limit=MAX_FUNCTION_CALLS
            )

    def _record_node_call(self, state: ExecutionState, node_id: str, node_type: str) -> None:
        """Записывает вызов ноды в историю."""
        if node_id not in state.node_history:
            state.node_history[node_id] = {"type": node_type, "calls": []}

        state.node_history[node_id]["calls"].append(
            {
                "response": state.response,
                "validation": state.validation,
            }
        )

    def _find_next_nodes(self, from_node: str, state: ExecutionState) -> List[str]:
        """
        Находит следующие ноды по edges.

        Возвращает ВСЕ ноды, для которых condition выполняется.
        Edge без condition - безусловный переход.
        Если несколько нод - параллельное выполнение.
        """
        seen: Set[str] = set()
        ordered: List[str] = []
        for to_node, _ in self._iter_active_transitions(from_node, state):
            if to_node not in seen:
                seen.add(to_node)
                ordered.append(to_node)
        return ordered

    def _evaluate_condition(self, condition: Any, state: ExecutionState) -> bool:
        """
        Вычисляет условие перехода.

        Поддерживаемые форматы:
        1. Объект с type='simple': {"type": "simple", "variable": "route", "operator": "==", "value": "order"}
        2. Объект с type='python': {"type": "python", "code": "def check(state): return state.get('route') == 'order'"}
        3. Legacy строка: "field == value", "field != value", и т.д.
        """
        if isinstance(condition, dict):
            return self._evaluate_condition_object(condition, state)
        
        return self._evaluate_condition_string(str(condition), state)

    def _evaluate_condition_object(self, condition: Dict[str, Any], state: ExecutionState) -> bool:
        """Вычисляет условие в новом объектном формате."""
        condition_type = condition.get("type")
        
        if condition_type == "simple":
            return self._evaluate_simple_condition(condition, state)
        if condition_type == "python":
            return self._evaluate_python_condition(condition.get("code", ""), state)

        raise ValueError(
            f"Неизвестный type условия ребра: {condition_type!r}, ожидаются 'simple' или 'python'"
        )

    def _evaluate_simple_condition(self, condition: Dict[str, Any], state: ExecutionState) -> bool:
        """Вычисляет простое условие: variable operator value."""
        variable = condition.get("variable", "")
        op_str = condition.get("operator", "==")
        value = condition.get("value", "")
        
        ops = {
            "==": operator.eq,
            "!=": operator.ne,
            ">": operator.gt,
            "<": operator.lt,
            ">=": operator.ge,
            "<=": operator.le,
            "in": lambda a, b: a in b if hasattr(b, "__contains__") else False,
        }
        
        op = ops.get(op_str, operator.eq)
        left = MappingResolver.get_nested_value(state, variable)
        right = self._parse_value(str(value)) if not isinstance(value, (bool, int, float)) else value
        
        try:
            return op(left, right)
        except TypeError as e:
            raise ValueError(
                f"Условие ребра: несовместимые типы для variable={variable!r} "
                f"op={op_str!r} left={left!r} right={right!r}"
            ) from e

    def _evaluate_python_condition(self, code: str, state: ExecutionState) -> bool:
        """
        Вычисляет Python условие через SafeEval.
        Код должен содержать функцию check(state) -> bool.
        """
        from apps.flows.src.eval.safe_eval import SafeEval
        from core.errors import SafeEvalError
        
        if not code or "def check" not in code:
            raise ValueError(
                "Python-условие ребра: требуется непустой код с функцией check(state)"
            )

        state_dict = state.model_dump(exclude_none=False)

        try:
            evaluator = SafeEval(variables=state.variables)
            check_fn = evaluator._compile(code, "check", auto_find=False)
            result = check_fn(state_dict)
            return bool(result)
        except SafeEvalError as e:
            raise ValueError(f"Python-условие ребра: ошибка SafeEval: {e}") from e
        except Exception as e:
            raise ValueError(f"Python-условие ребра: ошибка выполнения check(state): {e}") from e

    def _evaluate_condition_string(self, condition: str, state: ExecutionState) -> bool:
        """Вычисляет условие в legacy строковом формате."""
        # Двухсимвольные операторы раньше односимвольных: иначе "count <= 3" матчится как "count" > "= 3".
        patterns = [
            (r"(.+?)\s*==\s*(.+)", operator.eq),
            (r"(.+?)\s*!=\s*(.+)", operator.ne),
            (r"(.+?)\s*>=\s*(.+)", operator.ge),
            (r"(.+?)\s*<=\s*(.+)", operator.le),
            (r"(.+?)\s*>\s*(.+)", operator.gt),
            (r"(.+?)\s*<\s*(.+)", operator.lt),
        ]

        for pattern, op in patterns:
            match = re.match(pattern, condition.strip())
            if match:
                left_path = match.group(1).strip()
                right_value = match.group(2).strip()

                left = MappingResolver.get_nested_value(state, left_path)
                right = self._parse_value(right_value)

                try:
                    return op(left, right)
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
        config: Dict[str, Any], 
        variables: Optional[Dict[str, Any]] = None,
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
            nodes[node_id] = await create_node(node_id, node_config)

        # variables: параметр > config["resolved_variables"] > config["variables"]
        resolved_variables = (
            variables 
            or config.get("resolved_variables") 
            or config.get("variables", {})
        )

        return cls(
            flow_id=flow_id,
            name=config.get("name", ""),
            entry=config.get("entry", "main"),
            nodes=nodes,
            edges=config.get("edges", []),
            description=config.get("description", ""),
            tags=config.get("tags", []),
            variables=resolved_variables,
            config=config,
        )
