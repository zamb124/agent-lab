"""
Интеграционные тесты для output_mapping.

БЕЗ МОКОВ (кроме LLM согласно правилам проекта).

Тестирует unified output handling:
- output_mapping: маппинг полей результата в state
- Поведение без output_mapping: dict -> прямая запись в state
- Поведение без output_mapping: не-dict -> state.result
- Все типы нод: CodeNode, CodeNode, LlmNode, FlowNode
"""

import pytest
from apps.flows.src.runtime.nodes import (
    CodeNode,
    CodeNode,
    LlmNode,
)
from apps.flows.src.tools import InlineTool
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


class TestCodeNodeOutputMapping:
    """Тесты output_mapping для CodeNode."""

    @pytest.mark.asyncio
    async def test_dict_result_without_mapping_writes_directly(self):
        """CodeNode: dict без output_mapping -> поля пишутся напрямую в state."""
        code = """
async def run(state):
    return {"name": "John", "age": 25, "city": "Moscow"}
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        assert result.name == "John"
        assert result.age == 25
        assert result.city == "Moscow"

    @pytest.mark.asyncio
    async def test_dict_result_with_mapping(self):
        """CodeNode: dict с output_mapping -> маппинг полей."""
        code = """
async def run(state):
    return {"name": "John", "score": 95}
"""
        node = CodeNode(
            node_id="test_func",
            config={
                "code": code,
                "output_mapping": {"name": "user_name", "score": "user_score"}
            }
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
        """CodeNode: строка без output_mapping -> state.result."""
        code = """
async def run(state):
    return "simple string result"
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == "simple string result"

    @pytest.mark.asyncio
    async def test_number_result_without_mapping(self):
        """CodeNode: число без output_mapping -> state.result."""
        code = """
async def run(state):
    return 42
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_none_result(self):
        """CodeNode: None не меняет state."""
        code = """
async def run(state):
    return None
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state(existing_field="value")
        result = await node.run(state)
        
        assert result.existing_field == "value"
        # result поле не должно быть установлено
        assert not hasattr(result, "result") or result.result is None

    @pytest.mark.asyncio
    async def test_partial_mapping(self):
        """CodeNode: частичный маппинг - только указанные поля."""
        code = """
async def run(state):
    return {"field1": "value1", "field2": "value2", "field3": "value3"}
"""
        node = CodeNode(
            node_id="test_func",
            config={
                "code": code,
                "output_mapping": {"field1": "mapped_field1"}
            }
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
        """CodeNode: прямая модификация state + return dict."""
        code = """
async def run(state):
    state.direct_field = "modified_directly"
    return {"returned_field": "from_return"}
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        # Оба способа работают
        assert result.direct_field == "modified_directly"
        assert result.returned_field == "from_return"


class TestCodeNodeOutputMapping:
    """Тесты output_mapping для CodeNode."""

    @pytest.mark.asyncio
    async def test_dict_result_without_mapping(self):
        """CodeNode: dict без output_mapping -> поля пишутся напрямую."""
        node = CodeNode(
            node_id="test_tool",
            config={
                "code": """
async def execute(args, state):
    return {"status": "ok", "data": {"items": [1, 2, 3]}, "count": 3}
""",
                "input_mapping": {},
            },
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.status == "ok"
        assert result.data == {"items": [1, 2, 3]}
        assert result.count == 3

    @pytest.mark.asyncio
    async def test_dict_result_with_mapping(self):
        """CodeNode: dict с output_mapping -> маппинг полей."""
        node = CodeNode(
            node_id="test_tool",
            config={
                "code": """
async def execute(args, state):
    return {"result": "success", "value": 100}
""",
                "input_mapping": {},
                "output_mapping": {"result": "tool_status", "value": "tool_value"}
            },
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.tool_status == "success"
        assert result.tool_value == 100

    @pytest.mark.asyncio
    async def test_string_result_without_mapping(self):
        """CodeNode: строка без output_mapping -> state.result."""
        node = CodeNode(
            node_id="test_tool",
            config={
                "code": """
async def execute(args, state):
    return "Tool executed successfully"
""",
                "input_mapping": {},
            },
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == "Tool executed successfully"

    @pytest.mark.asyncio
    async def test_number_result_without_mapping(self):
        """CodeNode: число без output_mapping -> state.result."""
        node = CodeNode(
            node_id="test_tool",
            config={
                "code": """
async def execute(args, state):
    return args['x'] * args['y']
""",
                "input_mapping": {"x": 7, "y": 6},
            },
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == 42

    @pytest.mark.asyncio
    async def test_list_result_without_mapping(self):
        """CodeNode: список без output_mapping -> state.result."""
        node = CodeNode(
            node_id="test_tool",
            config={
                "code": """
async def execute(args, state):
    return [1, 2, 3, 4, 5]
""",
                "input_mapping": {},
            },
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result == [1, 2, 3, 4, 5]


class TestLlmNodeOutputMapping:
    """Тесты output_mapping для LlmNode (без structured output)."""

    @pytest.mark.asyncio
    async def test_response_without_mapping(self, mock_llm_with_queue):
        """LlmNode: response без output_mapping -> state.response."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Hello! How can I help?"}])
        
        node = LlmNode(
            node_id="test_agent",
            config={"prompt": "You are a helpful assistant"},
        )
        
        state = make_state(content="Hello")
        result = await node.run(state)
        
        assert result.response is not None
        assert "Hello" in result.response or len(result.response) > 0

    @pytest.mark.asyncio
    async def test_response_with_mapping(self, mock_llm_with_queue):
        """LlmNode: response с output_mapping -> маппинг."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Mock response"}])
        
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "You are a helpful assistant",
                "output_mapping": {"response": "agent_answer"}
            }
        )
        
        state = make_state(content="Hello")
        result = await node.run(state)
        
        assert result.agent_answer is not None


class TestLlmNodeStructuredOutput:
    """Тесты structured output для LlmNode."""

    @pytest.mark.asyncio
    async def test_structured_output_without_mapping(self, mock_llm_with_queue):
        """LlmNode: structured output без mapping -> поля напрямую."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "John", "age": 25}}])
        
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Extract user info from message",
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
        """LlmNode: structured output с mapping -> маппинг полей."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "Alice", "score": 95}}])
        
        node = LlmNode(
            node_id="test_agent",
            config={
                "prompt": "Extract user info",
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
async def run(state):
    return {}
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state(existing="value")
        result = await node.run(state)
        
        assert result.existing == "value"

    @pytest.mark.asyncio
    async def test_mapping_with_missing_keys(self):
        """Маппинг игнорирует отсутствующие ключи."""
        code = """
async def run(state):
    return {"field1": "value1"}
"""
        node = CodeNode(
            node_id="test_func",
            config={
                "code": code,
                "output_mapping": {"field1": "mapped1", "field2": "mapped2"}
            }
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
async def run(state):
    return {
        "user": {"name": "John", "profile": {"age": 25}},
        "metadata": {"timestamp": 12345}
    }
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        assert result.user == {"name": "John", "profile": {"age": 25}}
        assert result.metadata == {"timestamp": 12345}

    @pytest.mark.asyncio
    async def test_mapping_nested_dict_as_whole(self):
        """Маппинг вложенного dict целиком."""
        code = """
async def run(state):
    return {"data": {"items": [1, 2, 3], "count": 3}}
"""
        node = CodeNode(
            node_id="test_func",
            config={
                "code": code,
                "output_mapping": {"data": "response_data"}
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        assert result.response_data == {"items": [1, 2, 3], "count": 3}

    @pytest.mark.asyncio
    async def test_overwrite_existing_field(self):
        """Результат перезаписывает существующие поля state."""
        code = """
async def run(state):
    return {"field": "new_value"}
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state(field="old_value")
        result = await node.run(state)
        
        assert result.field == "new_value"

    @pytest.mark.asyncio
    async def test_bool_result_without_mapping(self):
        """Boolean результат -> state.result."""
        code = """
async def run(state):
    return True
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state()
        result = await node.run(state)
        
        assert result.result is True


class TestDataFlowWithOutputMapping:
    """Тесты передачи данных между нодами с output_mapping."""

    @pytest.mark.asyncio
    async def test_function_to_tool_with_mapping(self):
        """CodeNode с mapping -> CodeNode читает mapped поля."""
        # CodeNode возвращает dict, маппит в другие поля
        func_code = """
async def run(state):
    return {"raw_value": 10, "multiplier": 5}
"""
        func_node = CodeNode(
            node_id="prepare",
            config={
                "code": func_code,
                "output_mapping": {"raw_value": "input_value", "multiplier": "factor"}
            }
        )
        
        # CodeNode использует mapped поля
        tool_node = CodeNode(
            node_id="multiply",
            config={
                "code": "async def execute(args, state):\n    return args['x'] * args['y']",
                "input_mapping": {"x": "@state:input_value", "y": "@state:factor"},
            },
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
        """Цепочка CodeNode с output_mapping."""
        node1 = CodeNode(
            node_id="step1",
            config={
                "code": "async def execute(args, state):\n    return {'value': args['input'] * 2}",
                "input_mapping": {"input": 10},
                "output_mapping": {"value": "step1_result"}
            },
        )
        
        node2 = CodeNode(
            node_id="step2",
            config={
                "code": "async def execute(args, state):\n    return {'final': args['x'] + 5}",
                "input_mapping": {"x": "@state:step1_result"},
                "output_mapping": {"final": "final_result"}
            },
        )
        
        state = make_state()
        state = await node1.run(state)
        
        assert state.step1_result == 20
        
        state = await node2.run(state)
        
        assert state.final_result == 25


class TestExecutionStateReturnFromFunction:
    """Тесты возврата ExecutionState из CodeNode."""

    @pytest.mark.asyncio
    async def test_execution_state_return_merges(self):
        """CodeNode: возврат ExecutionState мержится в state."""
        code = """
async def run(state):
    state.modified_field = "modified"
    state.new_field = "new"
    return state
"""
        node = CodeNode(node_id="test_func", config={"code": code})
        
        state = make_state(existing="value")
        result = await node.run(state)
        
        # Все поля сохранились
        assert result.existing == "value"
        assert result.modified_field == "modified"
        assert result.new_field == "new"

    @pytest.mark.asyncio
    async def test_execution_state_return_ignores_output_mapping(self):
        """CodeNode: при возврате ExecutionState output_mapping игнорируется."""
        code = """
async def run(state):
    state.field1 = "value1"
    return state
"""
        node = CodeNode(
            node_id="test_func",
            config={
                "code": code,
                "output_mapping": {"field1": "mapped_field1"}
            }
        )
        
        state = make_state()
        result = await node.run(state)
        
        # При возврате ExecutionState маппинг не применяется
        # Поле записано как есть
        assert result.field1 == "value1"
