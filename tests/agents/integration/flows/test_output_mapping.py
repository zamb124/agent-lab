"""
Интеграционные тесты для output_mapping.

БЕЗ МОКОВ (кроме LLM согласно правилам проекта).

Тестирует unified output handling:
- output_mapping: маппинг полей результата в state
- Поведение без output_mapping: dict -> прямая запись в state
- Поведение без output_mapping: не-dict -> state.result
- Все типы нод: FunctionNode, ToolNode, ReactNode, AgentNode
"""

import pytest
from apps.agents.src.agent.nodes import (
    FunctionNode,
    ToolNode,
    ReactNode,
)
from apps.agents.src.tools import InlineTool
from core.state import ExecutionState


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
        "messages": [],
        "variables": {},
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestFunctionNodeOutputMapping:
    """Тесты output_mapping для FunctionNode."""

    @pytest.mark.asyncio
    async def test_dict_result_without_mapping_writes_directly(self):
        """FunctionNode: dict без output_mapping -> поля пишутся напрямую в state."""
        code = """
def run(state):
    return {"name": "John", "age": 25, "city": "Moscow"}
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        assert result.name == "John"
        assert result.age == 25
        assert result.city == "Moscow"

    @pytest.mark.asyncio
    async def test_dict_result_with_mapping(self):
        """FunctionNode: dict с output_mapping -> маппинг полей."""
        code = """
def run(state):
    return {"name": "John", "score": 95}
"""
        node = FunctionNode(
            node_id="test_func",
            code=code,
            config={"output_mapping": {"name": "user_name", "score": "user_score"}}
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.user_name == "John"
        assert result.user_score == 95
        # Оригинальные имена не должны быть записаны
        assert not hasattr(result, "name") or result.name is None
        assert not hasattr(result, "score") or result.score is None

    @pytest.mark.asyncio
    async def test_string_result_without_mapping(self):
        """FunctionNode: строка без output_mapping -> state.result."""
        code = """
def run(state):
    return "simple string result"
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == "simple string result"

    @pytest.mark.asyncio
    async def test_number_result_without_mapping(self):
        """FunctionNode: число без output_mapping -> state.result."""
        code = """
def run(state):
    return 42
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_none_result(self):
        """FunctionNode: None не меняет state."""
        code = """
def run(state):
    return None
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state(existing_field="value")
        result = await node.run(state)
        
        assert result.existing_field == "value"
        # result поле не должно быть установлено
        assert not hasattr(result, "result") or result.result is None

    @pytest.mark.asyncio
    async def test_partial_mapping(self):
        """FunctionNode: частичный маппинг - только указанные поля."""
        code = """
def run(state):
    return {"field1": "value1", "field2": "value2", "field3": "value3"}
"""
        node = FunctionNode(
            node_id="test_func",
            code=code,
            config={"output_mapping": {"field1": "mapped_field1"}}
        )
        
        state = make_state()
        result = await node.run(state)
        
        # Только field1 замаплен
        assert result.mapped_field1 == "value1"
        # field2 и field3 не записаны (маппинг есть, но они не в нём)
        assert not hasattr(result, "field2") or result.field2 is None
        assert not hasattr(result, "field3") or result.field3 is None

    @pytest.mark.asyncio
    async def test_direct_state_modification_plus_return(self):
        """FunctionNode: прямая модификация state + return dict."""
        code = """
def run(state):
    state.direct_field = "modified_directly"
    return {"returned_field": "from_return"}
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        # Оба способа работают
        assert result.direct_field == "modified_directly"
        assert result.returned_field == "from_return"


class TestToolNodeOutputMapping:
    """Тесты output_mapping для ToolNode."""

    @pytest.mark.asyncio
    async def test_dict_result_without_mapping(self):
        """ToolNode: dict без output_mapping -> поля пишутся напрямую."""
        tool = InlineTool(
            tool_id="data_tool",
            code="""
def execute(args, state):
    return {"status": "ok", "data": {"items": [1, 2, 3]}, "count": 3}
""",
        )
        
        node = ToolNode(
            node_id="test_tool",
            tool=tool,
            input_mapping={},
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.status == "ok"
        assert result.data == {"items": [1, 2, 3]}
        assert result.count == 3

    @pytest.mark.asyncio
    async def test_dict_result_with_mapping(self):
        """ToolNode: dict с output_mapping -> маппинг полей."""
        tool = InlineTool(
            tool_id="data_tool",
            code="""
def execute(args, state):
    return {"result": "success", "value": 100}
""",
        )
        
        node = ToolNode(
            node_id="test_tool",
            tool=tool,
            input_mapping={},
            config={"output_mapping": {"result": "tool_status", "value": "tool_value"}},
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.tool_status == "success"
        assert result.tool_value == 100

    @pytest.mark.asyncio
    async def test_string_result_without_mapping(self):
        """ToolNode: строка без output_mapping -> state.result."""
        tool = InlineTool(
            tool_id="text_tool",
            code="""
def execute(args, state):
    return "Tool executed successfully"
""",
        )
        
        node = ToolNode(
            node_id="test_tool",
            tool=tool,
            input_mapping={},
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == "Tool executed successfully"

    @pytest.mark.asyncio
    async def test_number_result_without_mapping(self):
        """ToolNode: число без output_mapping -> state.result."""
        tool = InlineTool(
            tool_id="calc_tool",
            code="""
def execute(args, state):
    return args['x'] * args['y']
""",
        )
        
        node = ToolNode(
            node_id="test_tool",
            tool=tool,
            input_mapping={"x": 7, "y": 6},
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_list_result_without_mapping(self):
        """ToolNode: список без output_mapping -> state.result."""
        tool = InlineTool(
            tool_id="list_tool",
            code="""
def execute(args, state):
    return [1, 2, 3, 4, 5]
""",
        )
        
        node = ToolNode(
            node_id="test_tool",
            tool=tool,
            input_mapping={},
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == [1, 2, 3, 4, 5]


class TestReactNodeOutputMapping:
    """Тесты output_mapping для ReactNode (без structured output)."""

    @pytest.mark.asyncio
    async def test_response_without_mapping(self, mock_llm_with_queue):
        """ReactNode: response без output_mapping -> state.response."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Hello! How can I help?"}])
        
        node = ReactNode(
            node_id="test_agent",
            prompt="You are a helpful assistant",
        )
        
        state = make_state(content="Hello")
        result = await node.run(state)
        
        assert result.response is not None
        assert "Hello" in result.response or len(result.response) > 0

    @pytest.mark.asyncio
    async def test_response_with_mapping(self, mock_llm_with_queue):
        """ReactNode: response с output_mapping -> маппинг."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Mock response"}])
        
        node = ReactNode(
            node_id="test_agent",
            prompt="You are a helpful assistant",
            config={
                "output_mapping": {"response": "agent_answer"}
            }
        )
        
        state = make_state(content="Hello")
        result = await node.run(state)
        
        assert result.agent_answer is not None


class TestReactNodeStructuredOutput:
    """Тесты structured output для ReactNode."""

    @pytest.mark.asyncio
    async def test_structured_output_without_mapping(self, mock_llm_with_queue):
        """ReactNode: structured output без mapping -> поля напрямую."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "John", "age": 25}}])
        
        node = ReactNode(
            node_id="test_agent",
            prompt="Extract user info from message",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "age": {"type": "integer"}
                    },
                    "required": ["name", "age"]
                }
            }
        )
        
        state = make_state(content="My name is John and I am 25 years old")
        result = await node.run(state)
        
        assert result.name == "John"
        assert result.age == 25

    @pytest.mark.asyncio
    async def test_structured_output_with_mapping(self, mock_llm_with_queue):
        """ReactNode: structured output с mapping -> маппинг полей."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "Alice", "score": 95}}])
        
        node = ReactNode(
            node_id="test_agent",
            prompt="Extract user info",
            config={
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "score": {"type": "integer"}
                    },
                    "required": ["name", "score"]
                },
                "output_mapping": {"name": "user_name", "score": "user_score"}
            }
        )
        
        state = make_state(content="Extract info")
        result = await node.run(state)
        
        assert result.user_name == "Alice"
        assert result.user_score == 95


class TestOutputMappingEdgeCases:
    """Тесты граничных случаев output_mapping."""

    @pytest.mark.asyncio
    async def test_empty_dict_result(self):
        """Пустой dict не меняет state."""
        code = """
def run(state):
    return {}
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state(existing="value")
        result = await node.run(state)
        
        assert result.existing == "value"

    @pytest.mark.asyncio
    async def test_mapping_with_missing_keys(self):
        """Маппинг игнорирует отсутствующие ключи."""
        code = """
def run(state):
    return {"field1": "value1"}
"""
        node = FunctionNode(
            node_id="test_func",
            code=code,
            config={"output_mapping": {"field1": "mapped1", "field2": "mapped2"}}
        )
        
        state = make_state()
        result = await node.run(state)
        
        # field1 замаплен
        assert result.mapped1 == "value1"
        # field2 не существует в результате - не записан
        assert not hasattr(result, "mapped2") or result.mapped2 is None

    @pytest.mark.asyncio
    async def test_nested_dict_in_result(self):
        """Вложенные dict в результате."""
        code = """
def run(state):
    return {
        "user": {"name": "John", "profile": {"age": 25}},
        "metadata": {"timestamp": 12345}
    }
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        assert result.user == {"name": "John", "profile": {"age": 25}}
        assert result.metadata == {"timestamp": 12345}

    @pytest.mark.asyncio
    async def test_mapping_nested_dict_as_whole(self):
        """Маппинг вложенного dict целиком."""
        code = """
def run(state):
    return {"data": {"items": [1, 2, 3], "count": 3}}
"""
        node = FunctionNode(
            node_id="test_func",
            code=code,
            config={"output_mapping": {"data": "response_data"}}
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.response_data == {"items": [1, 2, 3], "count": 3}

    @pytest.mark.asyncio
    async def test_overwrite_existing_field(self):
        """Результат перезаписывает существующие поля state."""
        code = """
def run(state):
    return {"field": "new_value"}
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state(field="old_value")
        result = await node.run(state)
        
        assert result.field == "new_value"

    @pytest.mark.asyncio
    async def test_bool_result_without_mapping(self):
        """Boolean результат -> state.result."""
        code = """
def run(state):
    return True
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result is True


class TestDataFlowWithOutputMapping:
    """Тесты передачи данных между нодами с output_mapping."""

    @pytest.mark.asyncio
    async def test_function_to_tool_with_mapping(self):
        """FunctionNode с mapping -> ToolNode читает mapped поля."""
        # FunctionNode возвращает dict, маппит в другие поля
        func_code = """
def run(state):
    return {"raw_value": 10, "multiplier": 5}
"""
        func_node = FunctionNode(
            node_id="prepare",
            code=func_code,
            config={"output_mapping": {"raw_value": "input_value", "multiplier": "factor"}}
        )
        
        # ToolNode использует mapped поля
        tool = InlineTool(
            tool_id="multiply",
            code="def execute(args, state):\n    return args['x'] * args['y']",
        )
        tool_node = ToolNode(
            node_id="multiply",
            tool=tool,
            input_mapping={"x": "@state:input_value", "y": "@state:factor"},
        )
        
        # Выполняем цепочку
        state = make_state()
        state = await func_node.run(state)
        
        # Проверяем что маппинг сработал
        assert state.input_value == 10
        assert state.factor == 5
        
        # Выполняем tool
        state = await tool_node.run(state)
        
        # Tool записал результат
        assert state.result == 50

    @pytest.mark.asyncio
    async def test_tool_chain_with_mapping(self):
        """Цепочка ToolNode с output_mapping."""
        tool1 = InlineTool(
            tool_id="step1",
            code="def execute(args, state):\n    return {'value': args['input'] * 2}",
        )
        node1 = ToolNode(
            node_id="step1",
            tool=tool1,
            input_mapping={"input": 10},
            config={"output_mapping": {"value": "step1_result"}},
        )
        
        tool2 = InlineTool(
            tool_id="step2",
            code="def execute(args, state):\n    return {'final': args['x'] + 5}",
        )
        node2 = ToolNode(
            node_id="step2",
            tool=tool2,
            input_mapping={"x": "@state:step1_result"},
            config={"output_mapping": {"final": "final_result"}},
        )
        
        state = make_state()
        state = await node1.run(state)
        
        assert state.step1_result == 20
        
        state = await node2.run(state)
        
        assert state.final_result == 25


class TestExecutionStateReturnFromFunction:
    """Тесты возврата ExecutionState из FunctionNode."""

    @pytest.mark.asyncio
    async def test_execution_state_return_merges(self):
        """FunctionNode: возврат ExecutionState мержится в state."""
        code = """
def run(state):
    state.modified_field = "modified"
    state.new_field = "new"
    return state
"""
        node = FunctionNode(node_id="test_func", code=code)
        
        state = make_state(existing="value")
        result = await node.run(state)
        
        # Все поля сохранились
        assert result.existing == "value"
        assert result.modified_field == "modified"
        assert result.new_field == "new"

    @pytest.mark.asyncio
    async def test_execution_state_return_ignores_output_mapping(self):
        """FunctionNode: при возврате ExecutionState output_mapping игнорируется."""
        code = """
def run(state):
    state.field1 = "value1"
    return state
"""
        node = FunctionNode(
            node_id="test_func",
            code=code,
            config={"output_mapping": {"field1": "mapped_field1"}}
        )
        
        state = make_state()
        result = await node.run(state)
        
        # При возврате ExecutionState маппинг не применяется
        # Поле записано как есть
        assert result.field1 == "value1"
