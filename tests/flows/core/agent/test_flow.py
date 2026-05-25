"""
Тесты для Flow.

Архитектура: nodes + edges + conditions
"""


from typing import override

import pytest

from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import (
    BaseNode,
    CodeNode,
    LlmNode,
    NodeInputs,
    NodeRunResult,
    create_node,
)
from core.errors import FlowInfiniteLoopError
from core.state import ExecutionState
from core.types import JsonObject, JsonValue, require_json_object
from core.variables import VariableResolver
from tests.flows.durable_runtime_harness import run_flow


def simple_condition(variable: str, operator: str, value: JsonValue) -> JsonObject:
    return require_json_object(
        {"type": "simple", "variable": variable, "operator": operator, "value": value},
        "edge.condition",
    )


class _PassthroughNonCodeNode(BaseNode):
    """Нода с типом не code: без дефолтного лимита заходов, только max_visits_per_run или итерации графа."""

    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = state, inputs
        return {}


class _StatePatchNode(BaseNode):
    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        patch = self.config["patch"]
        if not isinstance(patch, dict):
            raise ValueError("patch must be a dict")
        for key, value in patch.items():
            state[key] = value
        return state


class _CaptureVariablesNode(BaseNode):
    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        state.captured_variables = dict(state.variables)
        return state


class _GreetingFromVariablesNode(BaseNode):
    @override
    async def _run_impl(self, state: ExecutionState, inputs: NodeInputs) -> NodeRunResult:
        _ = inputs
        company = state.variables["company"]
        state.greeting = f"Welcome to {company}"
        return state


def patch_node(
    node_id: str,
    patch: JsonObject | None = None,
    *,
    container: FlowRuntimeContainer,
    node_type: str = "function",
    max_visits_per_run: int | None = None,
) -> _StatePatchNode:
    config: JsonObject = {"type": node_type, "patch": patch or {}}
    if max_visits_per_run is not None:
        config["max_visits_per_run"] = max_visits_per_run
    return _StatePatchNode(node_id, config=config, container=container)


def make_state(flow_id: str, unique_id: str, **extra: object) -> ExecutionState:
    context_id = f"context-{unique_id}"
    payload: dict[str, object] = {
        "task_id": f"task-{unique_id}",
        "context_id": context_id,
        "user_id": f"user-{unique_id}",
        "session_id": f"{flow_id}:{context_id}",
    }
    payload.update(extra)
    return ExecutionState.model_validate(payload)


async def run_test_flow(
    *,
    container: FlowRuntimeContainer,
    flow: Flow,
    unique_id: str,
    **state_extra: object,
) -> ExecutionState:
    return await run_flow(
        container=container,
        flow=flow,
        state=make_state(flow.flow_id, unique_id, **state_extra),
    )


class TestCodeNode:
    """Тесты CodeNode."""

    @pytest.mark.asyncio
    async def test_code_node_requires_durable_context_for_sync_function(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """CodeNode без NodeScheduled context не запускает remote runner."""

        node = CodeNode("test", config={
            "type": "code",
            "code": """async def run(args, state):
    state.result = "done"
    return {"result": "done"}"""
        }, container=container)
        with pytest.raises(RuntimeError, match="requires durable workflow instance"):
            _ = await node.run(make_state("code_context", unique_id))

    @pytest.mark.asyncio
    async def test_code_node_requires_durable_context_for_async_function(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """CodeNode исполняется только внутри durable workflow context."""

        node = CodeNode("test", config={
            "type": "code",
            "code": """async def run(args, state):
    state.async_result = "async_done"
    return {"async_result": "async_done"}"""
        }, container=container)
        with pytest.raises(RuntimeError, match="requires durable workflow instance"):
            _ = await node.run(make_state("code_context", unique_id))

    @pytest.mark.asyncio
    async def test_code_node_requires_durable_context_before_state_mutation(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """CodeNode не мутирует state без durable command boundary."""

        node = CodeNode("test", config={
            "type": "code",
            "code": """async def run(args, state):
    state.stage = "next"
    return {"stage": "next"}"""
        }, container=container)
        state = make_state("code_context", unique_id, stage="init")
        with pytest.raises(RuntimeError, match="requires durable workflow instance"):
            _ = await node.run(state)
        assert state["stage"] == "init"


class TestCreateNode:
    """Тесты фабрики create_node."""

    @pytest.mark.asyncio
    async def test_create_function_node(self, container: FlowRuntimeContainer):
        """create_node создает CodeNode."""
        config: JsonObject = {
            "type": "code",
            "code": "async def run(args, state):\n    state['initialized'] = True\n    return state",
        }

        node = await create_node("init", config, container=container)

        assert isinstance(node, CodeNode)

    @pytest.mark.asyncio
    async def test_create_node_rejects_missing_type(self, container: FlowRuntimeContainer):
        """create_node требует явный type."""
        config: JsonObject = {
            "code": "async def run(args, state):\n    return state",
        }

        with pytest.raises(ValueError, match="type is required"):
            _ = await create_node("missing_type", config, container=container)

    @pytest.mark.asyncio
    async def test_create_node_rejects_function_field_without_type(
        self, container: FlowRuntimeContainer
    ):
        """Поле function без type отклоняется строгим контрактом."""
        config: JsonObject = {"function": "math.sqrt"}

        with pytest.raises(ValueError, match="type is required"):
            _ = await create_node("missing_type", config, container=container)

    @pytest.mark.asyncio
    async def test_create_llm_node_node(self, container: FlowRuntimeContainer):
        """create_node создает LlmNode."""
        config: JsonObject = {
            "type": "llm_node",
            "prompt": "Test prompt",
            "tools": ["calculator"],
            "llm": {"model": "gpt-4o"},
        }

        node = await create_node("agent", config, container=container)

        assert isinstance(node, LlmNode)
        assert node.prompt_template == "Test prompt"

    @pytest.mark.asyncio
    async def test_create_node_raises_on_unknown_type(self, container: FlowRuntimeContainer):
        """create_node выбрасывает ошибку для неизвестного типа."""
        config: JsonObject = {"type": "unknown_type"}

        with pytest.raises(ValueError, match="Unknown node type"):
            _ = await create_node("test", config, container=container)


class TestFlowWithEdges:
    """Тесты Flow с edges."""

    @pytest.mark.asyncio
    async def test_flow_executes_linear_chain(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Flow выполняет линейную цепочку нод."""

        nodes: dict[str, BaseNode] = {
            "step1": patch_node("step1", {"step1": True}, container=container),
            "step2": patch_node("step2", {"step2": True}, container=container),
        }

        flow = Flow(
            flow_id="linear",
            name="Linear",
            entry="step1",
            nodes=nodes,
            edges=[
                {"from_node": "step1", "to_node": "step2"},
                {"from_node": "step2", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["step1"] is True
        assert result["step2"] is True
        assert result.current_nodes == []  # Flow завершён

    @pytest.mark.asyncio
    async def test_flow_with_condition_true(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Flow переходит по edge с условием true."""

        nodes: dict[str, BaseNode] = {
            "check": patch_node("check", {"valid": True}, container=container),
            "valid_path": patch_node("valid_path", {"path": "valid"}, container=container),
            "invalid_path": patch_node("invalid_path", {"path": "invalid"}, container=container),
        }

        flow = Flow(
            flow_id="conditional",
            name="Conditional",
            entry="check",
            nodes=nodes,
            edges=[
                {"from_node": "check", "to_node": "valid_path", "condition": simple_condition("valid", "==", True)},
                {"from_node": "check", "to_node": "invalid_path", "condition": simple_condition("valid", "==", False)},
                {"from_node": "valid_path", "to_node": None},
                {"from_node": "invalid_path", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["path"] == "valid"

    @pytest.mark.asyncio
    async def test_flow_with_condition_false(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Flow переходит по edge с условием false."""

        nodes: dict[str, BaseNode] = {
            "check": patch_node("check", {"valid": False}, container=container),
            "valid_path": patch_node("valid_path", {"path": "valid"}, container=container),
            "invalid_path": patch_node("invalid_path", {"path": "invalid"}, container=container),
        }

        flow = Flow(
            flow_id="conditional",
            name="Conditional",
            entry="check",
            nodes=nodes,
            edges=[
                {"from_node": "check", "to_node": "valid_path", "condition": simple_condition("valid", "==", True)},
                {"from_node": "check", "to_node": "invalid_path", "condition": simple_condition("valid", "==", False)},
                {"from_node": "valid_path", "to_node": None},
                {"from_node": "invalid_path", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["path"] == "invalid"

    @pytest.mark.asyncio
    async def test_flow_with_nested_condition(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Flow проверяет вложенное условие."""

        nodes: dict[str, BaseNode] = {
            "init": patch_node("init", {"validation": {"valid": True}}, container=container),
            "success": patch_node("success", {"result": "success"}, container=container),
        }

        flow = Flow(
            flow_id="nested",
            name="Nested",
            entry="init",
            nodes=nodes,
            edges=[
                {"from_node": "init", "to_node": "success", "condition": simple_condition("validation.valid", "==", True)},
                {"from_node": "success", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_flow_unconditional_edge(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Edge без condition - безусловный переход."""

        nodes: dict[str, BaseNode] = {
            "step1": patch_node("step1", {"step1": True}, container=container),
            "step2": patch_node("step2", {"step2": True}, container=container),
        }

        flow = Flow(
            flow_id="unconditional",
            name="Unconditional",
            entry="step1",
            nodes=nodes,
            edges=[
                {"from_node": "step1", "to_node": "step2"},  # Без condition
                {"from_node": "step2", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["step1"] is True
        assert result["step2"] is True

    @pytest.mark.asyncio
    async def test_flow_raises_on_missing_node(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Flow выбрасывает ошибку для несуществующей ноды."""

        nodes: dict[str, BaseNode] = {
            "start": patch_node("start", container=container),
        }

        flow = Flow(
            flow_id="broken",
            name="Broken",
            entry="nonexistent",
            nodes=nodes,
            edges=[],
            container=container,
        )

        with pytest.raises(ValueError, match="not found"):
            _ = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

    @pytest.mark.asyncio
    async def test_flow_raises_on_infinite_loop(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Flow выбрасывает ошибку при бесконечном цикле."""
        monkeypatch.setattr("apps.flows.src.runtime.flow.get_graph_max_iterations", lambda: 4)

        nodes: dict[str, BaseNode] = {
            "a": patch_node("a", container=container),
            "b": patch_node("b", container=container),
        }

        flow = Flow(
            flow_id="infinite",
            name="Infinite",
            entry="a",
            nodes=nodes,
            edges=[
                {"from_node": "a", "to_node": "b"},
                {"from_node": "b", "to_node": "a"},  # Бесконечный цикл
            ],
            container=container,
        )

        with pytest.raises(FlowInfiniteLoopError):
            _ = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

    @pytest.mark.asyncio
    async def test_flow_node_call_limit_resets_each_run(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Лимит вызовов code-ноды считается только в текущем Flow.run, без хвоста node_history."""

        nodes: dict[str, BaseNode] = {
            "prep": patch_node("prep", {"ran": True}, container=container, node_type="code"),
        }
        flow = Flow(
            flow_id="limit_reset",
            name="Limit reset",
            entry="prep",
            nodes=nodes,
            edges=[{"from_node": "prep", "to_node": None}],
            container=container,
        )
        state = make_state(flow.flow_id, unique_id)
        state.current_nodes = ["prep"]
        state.node_history["prep"] = {
            "type": "code",
            "calls": [{"response": None, "validation": None}] * 5,
        }
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.get("ran") is True
        calls = (result.node_history.get("prep") or {}).get("calls")
        assert isinstance(calls, list)
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_code_node_respects_max_visits_per_run(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        nodes: dict[str, BaseNode] = {
            "loop": patch_node(
                "loop",
                container=container,
                node_type="code",
                max_visits_per_run=3,
            ),
        }
        flow = Flow(
            flow_id="mvpr",
            name="mvpr",
            entry="loop",
            nodes=nodes,
            edges=[{"from_node": "loop", "to_node": "loop"}],
            container=container,
        )
        from core.errors import NodeCallLimitError

        with pytest.raises(NodeCallLimitError) as exc_info:
            _ = await run_test_flow(container=container, flow=flow, unique_id=unique_id)
        assert exc_info.value.payload["node_id"] == "loop"
        assert exc_info.value.payload["limit"] == 3

    @pytest.mark.asyncio
    async def test_non_code_cycle_hits_flow_iteration_cap_not_node_limit(
        self,
        container: FlowRuntimeContainer,
        unique_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.setattr("apps.flows.src.runtime.flow.get_graph_max_iterations", lambda: 4)
        nodes: dict[str, BaseNode] = {
            "a": _PassthroughNonCodeNode(
                "a",
                config={"type": "external_api"},
                container=container,
            ),
            "b": _PassthroughNonCodeNode(
                "b",
                config={"type": "external_api"},
                container=container,
            ),
        }
        flow = Flow(
            flow_id="ncc",
            name="ncc",
            entry="a",
            nodes=nodes,
            edges=[
                {"from_node": "a", "to_node": "b"},
                {"from_node": "b", "to_node": "a"},
            ],
            container=container,
        )
        from core.errors import FlowInfiniteLoopError

        with pytest.raises(FlowInfiniteLoopError):
            _ = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

    @pytest.mark.asyncio
    async def test_non_code_node_respects_max_visits_per_run(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        nodes: dict[str, BaseNode] = {
            "nc": _PassthroughNonCodeNode("nc", config={
                "type": "external_api",
                "max_visits_per_run": 2,
            }, container=container),
        }
        flow = Flow(
            flow_id="ncmv",
            name="ncmv",
            entry="nc",
            nodes=nodes,
            edges=[{"from_node": "nc", "to_node": "nc"}],
            container=container,
        )
        from core.errors import NodeCallLimitError

        with pytest.raises(NodeCallLimitError) as exc_info:
            _ = await run_test_flow(container=container, flow=flow, unique_id=unique_id)
        assert exc_info.value.payload["node_id"] == "nc"
        assert exc_info.value.payload["limit"] == 2

    @pytest.mark.asyncio
    async def test_flow_from_config(self, container: FlowRuntimeContainer):
        """Flow создаётся из JSON конфига."""
        config: JsonObject = {
            "flow_id": "config_flow",
            "name": "From Config",
            "entry": "init",
            "nodes": {
                "init": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [
                {"from_node": "init", "to_node": None},
            ],
        }

        flow = await Flow.from_config(config, container=container)

        assert flow.flow_id == "config_flow"
        assert flow.name == "From Config"
        assert "init" in flow.nodes
        assert isinstance(flow.nodes["init"], CodeNode)


class TestFlowVariables:
    """Тесты переменных flow."""

    @pytest.mark.asyncio
    async def test_variables_available_in_state(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Переменные flow доступны в state["variables"]."""

        nodes: dict[str, BaseNode] = {
            "main": _CaptureVariablesNode(
                "main",
                config={"type": "function"},
                container=container,
            ),
        }

        flow = Flow(
            flow_id="var_test",
            name="Variables Test",
            entry="main",
            nodes=nodes,
            edges=[{"from_node": "main", "to_node": None}],
            variables={"company": "TestCorp", "phone": "123-456"},
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["captured_variables"] == {"company": "TestCorp", "phone": "123-456"}

    @pytest.mark.asyncio
    async def test_function_can_use_variables(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Функция может использовать переменные из state."""

        nodes: dict[str, BaseNode] = {
            "main": _GreetingFromVariablesNode(
                "main",
                config={"type": "function"},
                container=container,
            ),
        }

        flow = Flow(
            flow_id="func_var_test",
            name="Function Variables Test",
            entry="main",
            nodes=nodes,
            edges=[{"from_node": "main", "to_node": None}],
            variables={"company": "Acme Inc"},
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["greeting"] == "Welcome to Acme Inc"

    @pytest.mark.asyncio
    async def test_flow_from_config_with_variables(self, container: FlowRuntimeContainer):
        """Flow.from_config принимает переменные."""
        config: JsonObject = {
            "flow_id": "var_config_flow",
            "name": "With Variables",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [{"from_node": "main", "to_node": None}],
        }
        variables: JsonObject = {"api_key": "secret123", "timeout": 30}

        flow = await Flow.from_config(config, variables=variables, container=container)

        assert flow.variables == {"api_key": "secret123", "timeout": 30}


class TestVariableResolver:
    """Тесты для подстановки переменных в промпты."""

    def test_render_simple_variable(self):
        """Простая подстановка переменной."""
        template = "Компания: {company_name}"
        variables: JsonObject = {"company_name": "TestCorp"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Компания: TestCorp"

    def test_render_multiple_variables(self):
        """Подстановка нескольких переменных."""
        template = "Добро пожаловать в {company}! Телефон: {phone}"
        variables: JsonObject = {"company": "Acme", "phone": "+7-999-123-45-67"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Добро пожаловать в Acme! Телефон: +7-999-123-45-67"

    def test_render_optional_variable_missing(self):
        """Опциональная переменная (отсутствует) - пустая строка."""
        template = "Name: {?name}"
        variables: JsonObject = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Name: "

    def test_render_optional_with_default(self):
        """Опциональная переменная со значением по умолчанию."""
        template = "Name: {?name|Anonymous}"
        variables: JsonObject = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Name: Anonymous"

    def test_render_preserves_unknown_variable_in_safe_mode(self):
        """Неизвестная переменная сохраняется в safe режиме."""
        template = "Value: {unknown_var}"
        variables: JsonObject = {}

        result = VariableResolver.render_template(template, local_vars=variables, safe=True)

        assert result == "Value: {unknown_var}"

    def test_render_prompt_like_template(self):
        """Рендеринг шаблона похожего на реальный промпт."""
        template = """Ты консультант компании {company_name}.

Правила:
- Телефон поддержки: {support_phone}
- Время работы: {?work_hours|9:00-18:00}

Приветствуй клиента по имени если известно: {?client_name}"""

        variables: JsonObject = {
            "company_name": "ИнгосСтрах",
            "support_phone": "8-800-100-77-55",
        }

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "ИнгосСтрах" in result
        assert "8-800-100-77-55" in result
        assert "9:00-18:00" in result  # значение по умолчанию
        assert "{?client_name}" not in result  # optional удалён


class TestFlowConditionEvaluation:
    """Тесты вычисления условий."""

    @pytest.mark.asyncio
    async def test_string_comparison(self, container: FlowRuntimeContainer, unique_id: str):
        """Сравнение со строкой."""

        nodes: dict[str, BaseNode] = {
            "init": patch_node("init", {"status": "active"}, container=container),
            "active": patch_node("active", {"result": "is_active"}, container=container),
        }

        flow = Flow(
            flow_id="string_cmp",
            name="String Comparison",
            entry="init",
            nodes=nodes,
            edges=[
                {"from_node": "init", "to_node": "active", "condition": simple_condition("status", "==", "active")},
                {"from_node": "active", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["result"] == "is_active"

    @pytest.mark.asyncio
    async def test_numeric_comparison(
        self, container: FlowRuntimeContainer, unique_id: str
    ):
        """Числовое сравнение."""

        nodes: dict[str, BaseNode] = {
            "init": patch_node("init", {"count": 5}, container=container),
            "high": patch_node("high", {"level": "high"}, container=container),
            "low": patch_node("low", {"level": "low"}, container=container),
        }

        flow = Flow(
            flow_id="numeric_cmp",
            name="Numeric Comparison",
            entry="init",
            nodes=nodes,
            edges=[
                {"from_node": "init", "to_node": "high", "condition": simple_condition("count", ">", 3)},
                {"from_node": "init", "to_node": "low", "condition": simple_condition("count", "<=", 3)},
                {"from_node": "high", "to_node": None},
                {"from_node": "low", "to_node": None},
            ],
            container=container,
        )

        result = await run_test_flow(container=container, flow=flow, unique_id=unique_id)

        assert result["level"] == "high"
