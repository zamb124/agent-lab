"""
Unit тесты для всех комбинаций input/check типов.

Комбинации:
- InputType: text, inline_code, node
- CheckType: string, inline_code, node

Все 9 комбинаций должны работать.
"""

from datetime import date

import pytest

from apps.flows.src.evaluation.runners.test_runner import TestRunner
from apps.flows.src.models import FlowConfig, NodeConfig
from apps.flows.src.models.flow_config import (
    CheckConfig,
    CheckType,
    InputConfig,
    InputType,
    TestCaseConfig,
    TestTurn,
)
from apps.flows.src.models.tool_reference import ToolReference
from core.state import ExecutionState


async def _noop_callable(state):
    return state


@pytest.fixture
def runner():
    """Создает TestRunner для тестов."""
    return TestRunner(
        target_id="test_flow:default",
        target_callable=_noop_callable,
        run_date=date.today(),
        iteration=1,
    )


@pytest.fixture
def execution_state():
    """Создает ExecutionState для тестов."""
    return ExecutionState(
        task_id="test-task",
        context_id="test-context",
        user_id="test-user",
        session_id="test-agent:test-context",
    )


class TestInputText:
    """Тесты для InputType.TEXT."""

    @pytest.mark.asyncio
    async def test_text_input(self, runner, execution_state):
        """Простой текстовый input."""
        input_config = InputConfig(type=InputType.TEXT, value="Привет!")
        text, files = await runner._get_input(input_config, execution_state)
        assert text == "Привет!"
        assert files is None

    @pytest.mark.asyncio
    async def test_text_input_empty(self, runner, execution_state):
        """Пустой текстовый input."""
        input_config = InputConfig(type=InputType.TEXT, value="")
        text, files = await runner._get_input(input_config, execution_state)
        assert text == ""


class TestInputFunction:
    """Тесты для InputType.INLINE_CODE (inline код)."""

    @pytest.mark.asyncio
    async def test_function_simple(self, runner, execution_state):
        """Простая inline функция."""
        input_config = InputConfig(
            type=InputType.INLINE_CODE,
            value='def generate():\n    return "Generated"',
        )
        text, files = await runner._get_input(input_config, execution_state)
        assert text == "Generated"

    @pytest.mark.asyncio
    async def test_function_with_logic(self, runner, execution_state):
        """Inline функция с логикой."""
        input_config = InputConfig(
            type=InputType.INLINE_CODE,
            value="""def generate():
    items = [1, 2, 3]
    return f"Sum: {sum(items)}"
""",
        )
        text, files = await runner._get_input(input_config, execution_state)
        assert text == "Sum: 6"

    @pytest.mark.asyncio
    async def test_function_multiline(self, runner, execution_state):
        """Многострочная inline функция."""
        input_config = InputConfig(
            type=InputType.INLINE_CODE,
            value="""def generate():
    greeting = "Hello"
    name = "World"
    return f"{greeting}, {name}!"
""",
        )
        text, files = await runner._get_input(input_config, execution_state)
        assert text == "Hello, World!"


class TestCheckString:
    """Тесты для CheckType.STRING."""

    def test_contains(self, runner):
        """contains: проверка."""
        assert runner._execute_string_checker("contains:привет", {}, "Привет!") is True
        assert runner._execute_string_checker("contains:пока", {}, "Привет!") is False

    def test_contains_multiple(self, runner):
        """contains: несколько слов."""
        assert runner._execute_string_checker("contains:hi|hello|привет", {}, "Hello!") is True
        assert runner._execute_string_checker("contains:bye|goodbye", {}, "Hello!") is False

    def test_not_contains(self, runner):
        """not_contains: проверка."""
        assert runner._execute_string_checker("not_contains:ошибка", {}, "Успех!") is True
        assert runner._execute_string_checker("not_contains:ошибка", {}, "Ошибка!") is False

    def test_regex(self, runner):
        """regex: проверка."""
        assert runner._execute_string_checker("regex:\\d+", {}, "Order 123") is True
        assert runner._execute_string_checker("regex:\\d+", {}, "No numbers") is False

    def test_length_min(self, runner):
        """length: минимум."""
        assert runner._execute_string_checker("length:5", {}, "Hello World") is True
        assert runner._execute_string_checker("length:100", {}, "Short") is False

    def test_length_max(self, runner):
        """length: максимум."""
        assert runner._execute_string_checker("length:-10", {}, "Short") is True
        assert runner._execute_string_checker("length:-5", {}, "Too long text") is False

    def test_length_range(self, runner):
        """length: диапазон."""
        assert runner._execute_string_checker("length:5-20", {}, "Hello World") is True
        assert runner._execute_string_checker("length:5-10", {}, "Too long for range") is False

    def test_state_equality(self, runner):
        """state: равенство."""
        assert runner._execute_string_checker("state:key == 'value'", {"key": "value"}, "") is True
        assert runner._execute_string_checker("state:key == 'other'", {"key": "value"}, "") is False

    def test_state_not_equal(self, runner):
        """state: неравенство."""
        assert runner._execute_string_checker("state:key != 'other'", {"key": "value"}, "") is True

    def test_state_numeric(self, runner):
        """state: числовые сравнения."""
        assert runner._execute_string_checker("state:count > 5", {"count": 10}, "") is True
        assert runner._execute_string_checker("state:count < 5", {"count": 10}, "") is False
        assert runner._execute_string_checker("state:count >= 10", {"count": 10}, "") is True
        assert runner._execute_string_checker("state:count <= 10", {"count": 10}, "") is True

    def test_state_nested(self, runner):
        """state: вложенные поля."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user={"profile": {"name": "John"}}
        )
        assert runner._execute_string_checker("state:user.profile.name == 'John'", state.model_dump(), "") is True

    def test_state_null(self, runner):
        """state: проверка null."""
        assert runner._execute_string_checker("state:field == null", {"field": None}, "") is True
        assert runner._execute_string_checker("state:field != null", {"field": "value"}, "") is True

    def test_state_boolean(self, runner):
        """state: boolean."""
        assert runner._execute_string_checker("state:active == true", {"active": True}, "") is True
        assert runner._execute_string_checker("state:active == false", {"active": False}, "") is True


class TestCheckFunction:
    """Тесты для CheckType.INLINE_CODE (inline код)."""

    @pytest.mark.asyncio
    async def test_function_returns_bool(self, runner, execution_state):
        """Inline checker возвращает bool -> нормализуется в Dict[str, float]."""
        check = CheckConfig(
            type=CheckType.INLINE_CODE,
            value='def check(state, response):\n    return "ok" in response',
        )
        result = await runner._execute_check(check, execution_state, "Everything is ok", [])
        assert result == {"result": 10.0}
        
        result = await runner._execute_check(check, execution_state, "Not good", [])
        assert result == {"result": 0.0}

    @pytest.mark.asyncio
    async def test_function_uses_state(self, runner):
        """Inline checker использует state."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            expected="success",
        )
        check = CheckConfig(
            type=CheckType.INLINE_CODE,
            value='def check(state, response):\n    return state.get("expected") in response',
        )
        result = await runner._execute_check(check, state, "Operation success", [])
        assert result == {"result": 10.0}

    @pytest.mark.asyncio
    async def test_function_returns_dict(self, runner, execution_state):
        """Inline checker возвращает dict scores -> нормализуется."""
        check = CheckConfig(
            type=CheckType.INLINE_CODE,
            value="""def check(state, response):
    return {
        "has_greeting": "hello" in response.lower(),
        "long_enough": len(response) > 10,
        "score": 8.5
    }""",
        )
        result = await runner._execute_check(check, execution_state, "Hello, this is a long response", [])
        assert result == {"has_greeting": 10.0, "long_enough": 10.0, "score": 8.5}

    @pytest.mark.asyncio
    async def test_function_complex_logic(self, runner, execution_state):
        """Inline checker со сложной логикой."""
        check = CheckConfig(
            type=CheckType.INLINE_CODE,
            value="""def check(state, response):
    words = response.lower().split()
    required = ["order", "confirmed"]
    return all(w in words for w in required)
""",
        )
        result = await runner._execute_check(check, execution_state, "Order has been confirmed", [])
        assert result == {"result": 10.0}
        
        result = await runner._execute_check(check, execution_state, "Request received", [])
        assert result == {"result": 0.0}


class TestTestCaseConfigAllCombinations:
    """Тесты для всех комбинаций input/check."""

    def test_text_string(self):
        """text -> string."""
        tc = TestCaseConfig(
            name="text_string",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.TEXT, value="Hello"),
                    check=CheckConfig(type=CheckType.STRING, value="contains:hello"),
                )
            ],
        )
        assert tc.turns[0].input.type == InputType.TEXT
        assert tc.turns[0].check.type == CheckType.STRING

    def test_text_function(self):
        """text -> function."""
        tc = TestCaseConfig(
            name="text_function",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.TEXT, value="Hello"),
                    check=CheckConfig(
                        type=CheckType.INLINE_CODE,
                        value='def check(s, r): return len(r) > 0',
                    ),
                )
            ],
        )
        assert tc.turns[0].check.type == CheckType.INLINE_CODE

    def test_text_agent(self):
        """text -> agent."""
        tc = TestCaseConfig(
            name="text_agent",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.TEXT, value="Hello"),
                    check=CheckConfig(type=CheckType.NODE, value="judge_agent_id"),
                )
            ],
        )
        assert tc.turns[0].check.type == CheckType.NODE

    def test_function_string(self):
        """function -> string."""
        tc = TestCaseConfig(
            name="function_string",
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.INLINE_CODE,
                        value='def generate(): return "Test"',
                    ),
                    check=CheckConfig(type=CheckType.STRING, value="length:1"),
                )
            ],
        )
        assert tc.turns[0].input.type == InputType.INLINE_CODE

    def test_function_function(self):
        """function -> function."""
        tc = TestCaseConfig(
            name="function_function",
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.INLINE_CODE,
                        value='def generate(): return "Test"',
                    ),
                    check=CheckConfig(
                        type=CheckType.INLINE_CODE,
                        value='def check(s, r): return True',
                    ),
                )
            ],
        )
        assert tc.turns[0].input.type == InputType.INLINE_CODE
        assert tc.turns[0].check.type == CheckType.INLINE_CODE

    def test_function_agent(self):
        """function -> agent."""
        tc = TestCaseConfig(
            name="function_agent",
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.INLINE_CODE,
                        value='def generate(): return "Test"',
                    ),
                    check=CheckConfig(
                        type=CheckType.NODE,
                        node=NodeConfig(
                            node_id="judge",
                            type="llm_node",
                            name="Judge",
                            prompt="Evaluate",
                        ),
                    ),
                )
            ],
        )
        assert tc.turns[0].check.node is not None

    def test_agent_string(self):
        """agent -> string (unusual but valid)."""
        tc = TestCaseConfig(
            name="agent_string",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.NODE, value="tester_id"),
                    check=CheckConfig(type=CheckType.STRING, value="length:1"),
                )
            ],
        )
        assert tc.turns[0].input.type == InputType.NODE

    def test_agent_function(self):
        """agent -> function."""
        tc = TestCaseConfig(
            name="agent_function",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.NODE, value="tester_id"),
                    check=CheckConfig(
                        type=CheckType.INLINE_CODE,
                        value='def check(s, r): return True',
                    ),
                )
            ],
        )
        assert tc.turns[0].check.type == CheckType.INLINE_CODE

    def test_agent_agent(self):
        """agent -> agent (full agent test)."""
        tc = TestCaseConfig(
            name="agent_agent",
            max_turns=5,
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.NODE, value="tester_id"),
                    check=CheckConfig(type=CheckType.NODE, value="judge_id"),
                )
            ],
        )
        assert tc.turns[0].input.type == InputType.NODE
        assert tc.turns[0].check.type == CheckType.NODE


class TestInlineAgentsWithTools:
    """Тесты для inline агентов с tools."""

    def test_inline_tester_with_tools(self):
        """Inline тестер с tools."""
        tc = TestCaseConfig(
            name="tester_with_tools",
            max_turns=5,
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.NODE,
                        node=NodeConfig(
                            node_id="smart_tester",
                            type="llm_node",
                            name="Smart Tester",
                            prompt="Ты умный тестер с инструментами.",
                            tools=[
                                ToolReference(tool_id="search", title="Search"),
                                ToolReference(tool_id="calculator", title="Calculator"),
                            ],
                        ),
                    ),
                    check=CheckConfig(type=CheckType.NODE, value="judge_id"),
                )
            ],
        )
        assert len(tc.turns[0].input.node["tools"]) == 2
        assert tc.turns[0].input.node["tools"][0]["tool_id"] == "search"

    def test_inline_judge_with_tools(self):
        """Inline судья с tools."""
        tc = TestCaseConfig(
            name="judge_with_tools",
            turns=[
                TestTurn(
                    input=InputConfig(type=InputType.TEXT, value="Test"),
                    check=CheckConfig(
                        type=CheckType.NODE,
                        node=NodeConfig(
                            node_id="smart_judge",
                            type="llm_node",
                            name="Smart Judge",
                            prompt="Оцени с помощью инструментов.",
                            tools=[
                                ToolReference(tool_id="analyze", title="Analyze"),
                            ],
                        ),
                    ),
                )
            ],
        )
        assert len(tc.turns[0].check.node["tools"]) == 1

    def test_both_agents_with_tools(self):
        """Оба агента с tools."""
        tc = TestCaseConfig(
            name="both_with_tools",
            max_turns=3,
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.NODE,
                        node=NodeConfig(
                            node_id="tester",
                            type="llm_node",
                            name="Tester",
                            prompt="Test",
                            tools=[ToolReference(tool_id="tool1", title="Tool 1")],
                        ),
                    ),
                    check=CheckConfig(
                        type=CheckType.NODE,
                        node=NodeConfig(
                            node_id="judge",
                            type="llm_node",
                            name="Judge",
                            prompt="Judge",
                            tools=[ToolReference(tool_id="tool2", title="Tool 2")],
                        ),
                    ),
                )
            ],
        )
        assert tc.turns[0].input.node["tools"][0]["tool_id"] == "tool1"
        assert tc.turns[0].check.node["tools"][0]["tool_id"] == "tool2"


class TestSerialization:
    """Тесты сериализации."""

    def test_full_serialization(self):
        """Полная сериализация/десериализация."""
        tc = TestCaseConfig(
            name="Full test",
            description="Full description",
            branch_ids=["default", "premium"],
            max_turns=10,
            timeout=600,
            turns=[
                TestTurn(
                    input=InputConfig(
                        type=InputType.NODE,
                        node=NodeConfig(
                            node_id="tester",
                            type="llm_node",
                            name="Tester",
                            prompt="Test prompt",
                            tools=[ToolReference(tool_id="calc", title="Calculator")],
                        ),
                    ),
                    check=CheckConfig(
                        type=CheckType.NODE,
                        node=NodeConfig(
                            node_id="judge",
                            type="llm_node",
                            name="Judge",
                            prompt="Judge prompt",
                        ),
                    ),
                ),
                TestTurn(
                    input=InputConfig(type=InputType.TEXT, value="Final check"),
                    check=CheckConfig(type=CheckType.STRING, value="contains:done"),
                ),
            ],
        )

        data = tc.model_dump()

        assert data["name"] == "Full test"
        assert data["max_turns"] == 10
        assert len(data["turns"]) == 2
        assert data["turns"][0]["input"]["node"]["tools"][0]["tool_id"] == "calc"

        restored = TestCaseConfig.model_validate(data)
        assert restored.name == "Full test"
        assert restored.turns[0].input.node["tools"][0]["tool_id"] == "calc"
        assert restored.turns[1].input.type == InputType.TEXT
