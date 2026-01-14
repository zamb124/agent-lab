"""
Тесты для Agent.

Архитектура: nodes + edges + conditions
"""

import pytest
from typing import Any, Dict

from apps.agents.src.agent.agent import Agent, AgentInfiniteLoopError
from apps.agents.src.agent.nodes import (
    BaseNode,
    FunctionNode,
    ReactNode,
    create_node,
)
from core.variables import VariableResolver


class TestFunctionNode:
    """Тесты FunctionNode."""

    @pytest.mark.asyncio
    async def test_function_node_executes_sync_function(self, make_test_state):
        """FunctionNode выполняет синхронную функцию."""

        def my_func(state):
            state["result"] = "done"
            return state

        node = FunctionNode("test", my_func)
        state = make_test_state()
        result = await node.run(state)

        assert result["result"] == "done"

    @pytest.mark.asyncio
    async def test_function_node_executes_async_function(self, make_test_state):
        """FunctionNode выполняет асинхронную функцию."""

        async def my_async_func(state):
            state["async_result"] = "async_done"
            return state

        node = FunctionNode("test", my_async_func)
        state = make_test_state()
        result = await node.run(state)

        assert result["async_result"] == "async_done"

    @pytest.mark.asyncio
    async def test_function_node_changes_stage(self, make_test_state):
        """FunctionNode может менять stage."""

        def set_stage(state):
            state["stage"] = "next"
            return state

        node = FunctionNode("test", set_stage)
        state = make_test_state(stage="init")
        result = await node.run(state)

        assert result["stage"] == "next"


class TestCreateNode:
    """Тесты фабрики create_node."""

    @pytest.mark.asyncio
    async def test_create_function_node(self):
        """create_node создает FunctionNode."""
        config = {
            "type": "function",
            "code": "def run(state):\n    state['initialized'] = True\n    return state",
        }

        node = await create_node("init", config)

        assert isinstance(node, FunctionNode)

    @pytest.mark.asyncio
    async def test_create_react_node_node(self):
        """create_node создает ReactNode."""
        config = {
            "type": "react_node",
            "prompt": "Test prompt",
            "tools": ["calculator"],
            "llm": {"model": "gpt-4o"},
        }

        node = await create_node("agent", config)

        assert isinstance(node, ReactNode)
        assert node.prompt_template == "Test prompt"

    @pytest.mark.asyncio
    async def test_create_node_raises_on_unknown_type(self):
        """create_node выбрасывает ошибку для неизвестного типа."""
        config = {"type": "unknown_type"}

        with pytest.raises(ValueError, match="Unknown node type"):
            await create_node("test", config)


class TestFlowWithEdges:
    """Тесты Agent с edges."""

    @pytest.mark.asyncio
    async def test_flow_executes_linear_chain(self):
        """Agent выполняет линейную цепочку нод."""

        def step1(state):
            state["step1"] = True
            return state

        def step2(state):
            state["step2"] = True
            return state

        nodes = {
            "step1": FunctionNode("step1", step1),
            "step2": FunctionNode("step2", step2),
        }

        flow = Agent(
            agent_id="linear",
            name="Linear",
            entry="step1",
            nodes=nodes,
            edges=[
                {"from": "step1", "to": "step2"},
                {"from": "step2", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["step1"] is True
        assert result["step2"] is True
        assert result.current_nodes == []  # Agent завершён

    @pytest.mark.asyncio
    async def test_flow_with_condition_true(self):
        """Agent переходит по edge с условием true."""

        def set_valid(state):
            state["valid"] = True
            return state

        def on_valid(state):
            state["path"] = "valid"
            return state

        def on_invalid(state):
            state["path"] = "invalid"
            return state

        nodes = {
            "check": FunctionNode("check", set_valid),
            "valid_path": FunctionNode("valid_path", on_valid),
            "invalid_path": FunctionNode("invalid_path", on_invalid),
        }

        flow = Agent(
            agent_id="conditional",
            name="Conditional",
            entry="check",
            nodes=nodes,
            edges=[
                {"from": "check", "to": "valid_path", "condition": "valid == true"},
                {"from": "check", "to": "invalid_path", "condition": "valid == false"},
                {"from": "valid_path", "to": None},
                {"from": "invalid_path", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["path"] == "valid"

    @pytest.mark.asyncio
    async def test_flow_with_condition_false(self):
        """Agent переходит по edge с условием false."""

        def set_invalid(state):
            state["valid"] = False
            return state

        def on_valid(state):
            state["path"] = "valid"
            return state

        def on_invalid(state):
            state["path"] = "invalid"
            return state

        nodes = {
            "check": FunctionNode("check", set_invalid),
            "valid_path": FunctionNode("valid_path", on_valid),
            "invalid_path": FunctionNode("invalid_path", on_invalid),
        }

        flow = Agent(
            agent_id="conditional",
            name="Conditional",
            entry="check",
            nodes=nodes,
            edges=[
                {"from": "check", "to": "valid_path", "condition": "valid == true"},
                {"from": "check", "to": "invalid_path", "condition": "valid == false"},
                {"from": "valid_path", "to": None},
                {"from": "invalid_path", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["path"] == "invalid"

    @pytest.mark.asyncio
    async def test_flow_with_nested_condition(self):
        """Agent проверяет вложенное условие."""

        def set_nested(state):
            state["validation"] = {"valid": True}
            return state

        def success(state):
            state["result"] = "success"
            return state

        nodes = {
            "init": FunctionNode("init", set_nested),
            "success": FunctionNode("success", success),
        }

        flow = Agent(
            agent_id="nested",
            name="Nested",
            entry="init",
            nodes=nodes,
            edges=[
                {"from": "init", "to": "success", "condition": "validation.valid == true"},
                {"from": "success", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["result"] == "success"

    @pytest.mark.asyncio
    async def test_flow_unconditional_edge(self):
        """Edge без condition - безусловный переход."""

        def step1(state):
            state["step1"] = True
            return state

        def step2(state):
            state["step2"] = True
            return state

        nodes = {
            "step1": FunctionNode("step1", step1),
            "step2": FunctionNode("step2", step2),
        }

        flow = Agent(
            agent_id="unconditional",
            name="Unconditional",
            entry="step1",
            nodes=nodes,
            edges=[
                {"from": "step1", "to": "step2"},  # Без condition
                {"from": "step2", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["step1"] is True
        assert result["step2"] is True

    @pytest.mark.asyncio
    async def test_flow_raises_on_missing_node(self):
        """Agent выбрасывает ошибку для несуществующей ноды."""

        nodes = {
            "start": FunctionNode("start", lambda s: s),
        }

        flow = Agent(
            agent_id="broken",
            name="Broken",
            entry="nonexistent",
            nodes=nodes,
            edges=[],
        )

        from core.state import ExecutionState
        with pytest.raises(ValueError, match="not found"):
            await flow.run(ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            ))

    @pytest.mark.asyncio
    async def test_flow_raises_on_infinite_loop(self):
        """Agent выбрасывает ошибку при бесконечном цикле."""

        def noop(state):
            return state

        nodes = {
            "a": FunctionNode("a", noop),
            "b": FunctionNode("b", noop),
        }

        flow = Agent(
            agent_id="infinite",
            name="Infinite",
            entry="a",
            nodes=nodes,
            edges=[
                {"from": "a", "to": "b"},
                {"from": "b", "to": "a"},  # Бесконечный цикл
            ],
        )

        from core.state import ExecutionState
        with pytest.raises(AgentInfiniteLoopError):
            await flow.run(ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            ))

    @pytest.mark.asyncio
    async def test_flow_from_config(self):
        """Agent создается из JSON конфига."""
        config = {
            "id": "config_flow",
            "name": "From Config",
            "entry": "init",
            "nodes": {
                "init": {
                    "type": "function",
                    "code": "def run(state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [
                {"from": "init", "to": None},
            ],
        }

        flow = await Agent.from_config(config)

        assert flow.agent_id == "config_flow"
        assert flow.name == "From Config"
        assert "init" in flow.nodes
        assert isinstance(flow.nodes["init"], FunctionNode)


class TestFlowVariables:
    """Тесты переменных flow."""

    @pytest.mark.asyncio
    async def test_variables_available_in_state(self):
        """Переменные flow доступны в state["variables"]."""
        captured_variables = {}

        def capture_variables(state: Dict[str, Any]) -> Dict[str, Any]:
            captured_variables.update(state.get("variables", {}))
            return state

        nodes = {
            "main": FunctionNode("main", capture_variables),
        }

        flow = Agent(
            agent_id="var_test",
            name="Variables Test",
            entry="main",
            nodes=nodes,
            edges=[{"from": "main", "to": None}],
            variables={"company": "TestCorp", "phone": "123-456"},
        )

        from core.state import ExecutionState
        await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert captured_variables == {"company": "TestCorp", "phone": "123-456"}

    @pytest.mark.asyncio
    async def test_function_can_use_variables(self):
        """Функция может использовать переменные из state."""

        def use_variables(state: Dict[str, Any]) -> Dict[str, Any]:
            variables = state.get("variables", {})
            state["greeting"] = f"Welcome to {variables.get('company', 'Unknown')}"
            return state

        nodes = {
            "main": FunctionNode("main", use_variables),
        }

        flow = Agent(
            agent_id="func_var_test",
            name="Function Variables Test",
            entry="main",
            nodes=nodes,
            edges=[{"from": "main", "to": None}],
            variables={"company": "Acme Inc"},
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["greeting"] == "Welcome to Acme Inc"

    @pytest.mark.asyncio
    async def test_flow_from_config_with_variables(self):
        """Agent.from_config принимает переменные."""
        config = {
            "id": "var_config_flow",
            "name": "With Variables",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "function",
                    "code": "def run(state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [{"from": "main", "to": None}],
        }
        variables = {"api_key": "secret123", "timeout": 30}

        flow = await Agent.from_config(config, variables=variables)

        assert flow.variables == {"api_key": "secret123", "timeout": 30}


class TestVariableResolver:
    """Тесты для подстановки переменных в промпты."""

    def test_render_simple_variable(self):
        """Простая подстановка переменной."""
        template = "Компания: {company_name}"
        variables = {"company_name": "TestCorp"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Компания: TestCorp"

    def test_render_multiple_variables(self):
        """Подстановка нескольких переменных."""
        template = "Добро пожаловать в {company}! Телефон: {phone}"
        variables = {"company": "Acme", "phone": "+7-999-123-45-67"}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Добро пожаловать в Acme! Телефон: +7-999-123-45-67"

    def test_render_optional_variable_missing(self):
        """Опциональная переменная (отсутствует) - пустая строка."""
        template = "Name: {?name}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Name: "

    def test_render_optional_with_default(self):
        """Опциональная переменная со значением по умолчанию."""
        template = "Name: {?name|Anonymous}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables)

        assert result == "Name: Anonymous"

    def test_render_preserves_unknown_variable_in_safe_mode(self):
        """Неизвестная переменная сохраняется в safe режиме."""
        template = "Value: {unknown_var}"
        variables = {}

        result = VariableResolver.render_template(template, local_vars=variables, safe=True)

        assert result == "Value: {unknown_var}"

    def test_render_prompt_like_template(self):
        """Рендеринг шаблона похожего на реальный промпт."""
        template = """Ты консультант компании {company_name}.

Правила:
- Телефон поддержки: {support_phone}
- Время работы: {?work_hours|9:00-18:00}

Приветствуй клиента по имени если известно: {?client_name}"""

        variables = {
            "company_name": "ИнгосСтрах",
            "support_phone": "8-800-100-77-55",
        }

        result = VariableResolver.render_template(template, local_vars=variables)

        assert "ИнгосСтрах" in result
        assert "8-800-100-77-55" in result
        assert "9:00-18:00" in result  # default value
        assert "{?client_name}" not in result  # optional removed


class TestFlowConditionEvaluation:
    """Тесты вычисления условий."""

    @pytest.mark.asyncio
    async def test_string_comparison(self):
        """Сравнение со строкой."""

        def set_status(state):
            state["status"] = "active"
            return state

        def on_active(state):
            state["result"] = "is_active"
            return state

        nodes = {
            "init": FunctionNode("init", set_status),
            "active": FunctionNode("active", on_active),
        }

        flow = Agent(
            agent_id="string_cmp",
            name="String Comparison",
            entry="init",
            nodes=nodes,
            edges=[
                {"from": "init", "to": "active", "condition": 'status == "active"'},
                {"from": "active", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["result"] == "is_active"

    @pytest.mark.asyncio
    async def test_numeric_comparison(self):
        """Числовое сравнение."""

        def set_count(state):
            state["count"] = 5
            return state

        def high(state):
            state["level"] = "high"
            return state

        def low(state):
            state["level"] = "low"
            return state

        nodes = {
            "init": FunctionNode("init", set_count),
            "high": FunctionNode("high", high),
            "low": FunctionNode("low", low),
        }

        flow = Agent(
            agent_id="numeric_cmp",
            name="Numeric Comparison",
            entry="init",
            nodes=nodes,
            edges=[
                {"from": "init", "to": "high", "condition": "count > 3"},
                {"from": "init", "to": "low", "condition": "count <= 3"},
                {"from": "high", "to": None},
                {"from": "low", "to": None},
            ],
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["level"] == "high"
