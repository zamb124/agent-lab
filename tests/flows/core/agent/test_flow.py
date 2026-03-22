"""
Тесты для Flow.

Архитектура: nodes + edges + conditions
"""

import pytest
from typing import Any, Dict

from apps.flows.src.runtime.flow import Flow, FlowInfiniteLoopError
from apps.flows.src.runtime.nodes import (
    BaseNode,
    CodeNode,
    LlmNode,
    create_node,
)
from core.variables import VariableResolver


class TestCodeNode:
    """Тесты CodeNode."""

    @pytest.mark.asyncio
    async def test_function_node_executes_sync_function(self, make_test_state):
        """CodeNode выполняет синхронную функцию."""

        node = CodeNode("test", config={
            "code": """def execute(args, state):
    state.result = "done"
    return {"result": "done"}"""
        })
        state = make_test_state()
        result = await node.run(state)

        assert result["result"] == "done"

    @pytest.mark.asyncio
    async def test_function_node_executes_async_function(self, make_test_state):
        """CodeNode выполняет асинхронную функцию."""

        node = CodeNode("test", config={
            "code": """async def execute(args, state):
    state.async_result = "async_done"
    return {"async_result": "async_done"}"""
        })
        state = make_test_state()
        result = await node.run(state)

        assert result["async_result"] == "async_done"

    @pytest.mark.asyncio
    async def test_function_node_changes_stage(self, make_test_state):
        """CodeNode может менять stage."""

        node = CodeNode("test", config={
            "code": """def execute(args, state):
    state.stage = "next"
    return {"stage": "next"}"""
        })
        state = make_test_state(stage="init")
        result = await node.run(state)

        assert result["stage"] == "next"


class TestCreateNode:
    """Тесты фабрики create_node."""

    @pytest.mark.asyncio
    async def test_create_function_node(self):
        """create_node создает CodeNode."""
        config = {
            "type": "code",
            "code": "def run(state):\n    state['initialized'] = True\n    return state",
        }

        node = await create_node("init", config)

        assert isinstance(node, CodeNode)

    @pytest.mark.asyncio
    async def test_create_llm_node_node(self):
        """create_node создает LlmNode."""
        config = {
            "type": "llm_node",
            "prompt": "Test prompt",
            "tools": ["calculator"],
            "llm": {"model": "gpt-4o"},
        }

        node = await create_node("agent", config)

        assert isinstance(node, LlmNode)
        assert node.prompt_template == "Test prompt"

    @pytest.mark.asyncio
    async def test_create_node_raises_on_unknown_type(self):
        """create_node выбрасывает ошибку для неизвестного типа."""
        config = {"type": "unknown_type"}

        with pytest.raises(ValueError, match="Unknown node type"):
            await create_node("test", config)


class TestFlowWithEdges:
    """Тесты Flow с edges."""

    @pytest.mark.asyncio
    async def test_flow_executes_linear_chain(self):
        """Flow выполняет линейную цепочку нод."""

        nodes = {
            "step1": CodeNode("step1", config={
                "code": """def execute(args, state):
    state.step1 = True
    return {"step1": True}"""
            }),
            "step2": CodeNode("step2", config={
                "code": """def execute(args, state):
    state.step2 = True
    return {"step2": True}"""
            }),
        }

        flow = Flow(
            flow_id="linear",
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
        assert result.current_nodes == []  # Flow завершён

    @pytest.mark.asyncio
    async def test_flow_with_condition_true(self):
        """Flow переходит по edge с условием true."""

        nodes = {
            "check": CodeNode("check", config={
                "code": """def execute(args, state):
    state.valid = True
    return {"valid": True}"""
            }),
            "valid_path": CodeNode("valid_path", config={
                "code": """def execute(args, state):
    state.path = "valid"
    return {"path": "valid"}"""
            }),
            "invalid_path": CodeNode("invalid_path", config={
                "code": """def execute(args, state):
    state.path = "invalid"
    return {"path": "invalid"}"""
            }),
        }

        flow = Flow(
            flow_id="conditional",
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
        """Flow переходит по edge с условием false."""

        nodes = {
            "check": CodeNode("check", config={
                "code": """def execute(args, state):
    state.valid = False
    return {"valid": False}"""
            }),
            "valid_path": CodeNode("valid_path", config={
                "code": """def execute(args, state):
    state.path = "valid"
    return {"path": "valid"}"""
            }),
            "invalid_path": CodeNode("invalid_path", config={
                "code": """def execute(args, state):
    state.path = "invalid"
    return {"path": "invalid"}"""
            }),
        }

        flow = Flow(
            flow_id="conditional",
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
        """Flow проверяет вложенное условие."""

        nodes = {
            "init": CodeNode("init", config={
                "code": """def execute(args, state):
    state.validation = {"valid": True}
    return {"validation": {"valid": True}}"""
            }),
            "success": CodeNode("success", config={
                "code": """def execute(args, state):
    state.result = "success"
    return {"result": "success"}"""
            }),
        }

        flow = Flow(
            flow_id="nested",
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

        nodes = {
            "step1": CodeNode("step1", config={
                "code": """def execute(args, state):
    state.step1 = True
    return {"step1": True}"""
            }),
            "step2": CodeNode("step2", config={
                "code": """def execute(args, state):
    state.step2 = True
    return {"step2": True}"""
            }),
        }

        flow = Flow(
            flow_id="unconditional",
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
        """Flow выбрасывает ошибку для несуществующей ноды."""

        nodes = {
            "start": CodeNode("start", config={
                "code": """def execute(args, state):
    return {}"""
            }),
        }

        flow = Flow(
            flow_id="broken",
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
        """Flow выбрасывает ошибку при бесконечном цикле."""

        nodes = {
            "a": CodeNode("a", config={
                "code": """def execute(args, state):
    return {}"""
            }),
            "b": CodeNode("b", config={
                "code": """def execute(args, state):
    return {}"""
            }),
        }

        flow = Flow(
            flow_id="infinite",
            name="Infinite",
            entry="a",
            nodes=nodes,
            edges=[
                {"from": "a", "to": "b"},
                {"from": "b", "to": "a"},  # Бесконечный цикл
            ],
        )

        from core.state import ExecutionState
        from core.errors import NodeCallLimitError
        with pytest.raises((FlowInfiniteLoopError, NodeCallLimitError)):
            await flow.run(ExecutionState(
                task_id="test-task",
                context_id="test-context",
                user_id="test-user",
                session_id="test-agent:test-context",
            ))

    @pytest.mark.asyncio
    async def test_flow_from_config(self):
        """Flow создаётся из JSON конфига."""
        config = {
            "id": "config_flow",
            "name": "From Config",
            "entry": "init",
            "nodes": {
                "init": {
                    "type": "code",
                    "code": "def run(state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [
                {"from": "init", "to": None},
            ],
        }

        flow = await Flow.from_config(config)

        assert flow.flow_id == "config_flow"
        assert flow.name == "From Config"
        assert "init" in flow.nodes
        assert isinstance(flow.nodes["init"], CodeNode)


class TestFlowVariables:
    """Тесты переменных flow."""

    @pytest.mark.asyncio
    async def test_variables_available_in_state(self):
        """Переменные flow доступны в state["variables"]."""

        nodes = {
            "main": CodeNode("main", config={
                "code": """def execute(args, state):
    state.captured_variables = dict(state.variables)
    return {"captured_variables": dict(state.variables)}""",
            }),
        }

        flow = Flow(
            flow_id="var_test",
            name="Variables Test",
            entry="main",
            nodes=nodes,
            edges=[{"from": "main", "to": None}],
            variables={"company": "TestCorp", "phone": "123-456"},
        )

        from core.state import ExecutionState
        result = await flow.run(ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
        ))

        assert result["captured_variables"] == {"company": "TestCorp", "phone": "123-456"}

    @pytest.mark.asyncio
    async def test_function_can_use_variables(self):
        """Функция может использовать переменные из state."""

        nodes = {
            "main": CodeNode("main", config={
                "code": """def execute(args, state):
    variables = state.variables
    company = variables.get('company', 'Unknown')
    state.greeting = f"Welcome to {company}"
    return {"greeting": f"Welcome to {company}"}""",
            }),
        }

        flow = Flow(
            flow_id="func_var_test",
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
        """Flow.from_config принимает переменные."""
        config = {
            "id": "var_config_flow",
            "name": "With Variables",
            "entry": "main",
            "nodes": {
                "main": {
                    "type": "code",
                    "code": "def run(state):\n    state['initialized'] = True\n    return state",
                },
            },
            "edges": [{"from": "main", "to": None}],
        }
        variables = {"api_key": "secret123", "timeout": 30}

        flow = await Flow.from_config(config, variables=variables)

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

        nodes = {
            "init": CodeNode("init", config={
                "code": """def execute(args, state):
    state.status = "active"
    return {"status": "active"}"""
            }),
            "active": CodeNode("active", config={
                "code": """def execute(args, state):
    state.result = "is_active"
    return {"result": "is_active"}"""
            }),
        }

        flow = Flow(
            flow_id="string_cmp",
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

        nodes = {
            "init": CodeNode("init", config={
                "code": """def execute(args, state):
    state.count = 5
    return {"count": 5}"""
            }),
            "high": CodeNode("high", config={
                "code": """def execute(args, state):
    state.level = "high"
    return {"level": "high"}"""
            }),
            "low": CodeNode("low", config={
                "code": """def execute(args, state):
    state.level = "low"
    return {"level": "low"}"""
            }),
        }

        flow = Flow(
            flow_id="numeric_cmp",
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
