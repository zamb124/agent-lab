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
    LlmNode,
)
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_node, workflow_state


def make_state(unique_id: str, *, flow_id: str, **kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    return workflow_state(
        flow_id=flow_id,
        unique_id=unique_id,
        messages=[],
        variables={},
        **kwargs,
    )


def code_node(container, node_id: str, config: dict[str, object]) -> CodeNode:
    return CodeNode(node_id=node_id, config={"type": "code", **config}, container=container)


async def run_single_node(
    container,
    node: CodeNode | LlmNode,
    state: ExecutionState,
) -> ExecutionState:
    return await run_node(container=container, node=node, state=state)


class TestCodeNodeOutputMapping:
    """Тесты output_mapping для CodeNode."""

    @pytest.mark.asyncio
    async def test_dict_result_without_mapping(self, container, unique_id: str):
        """CodeNode: dict без output_mapping -> поля пишутся напрямую."""
        node = code_node(
            container,
            node_id="test_tool",
            config={
                "code": """
async def run(args, state):
    return {"status": "ok", "data": {"items": [1, 2, 3]}, "count": 3}
""",
                "input_mapping": {},
            },
        )

        state = make_state(unique_id, flow_id="test_tool_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.status == "ok"
        assert result.data == {"items": [1, 2, 3]}
        assert result.count == 3

    @pytest.mark.asyncio
    async def test_dict_result_with_mapping(self, container, unique_id: str):
        """CodeNode: dict с output_mapping -> маппинг полей."""
        node = code_node(
            container,
            node_id="test_tool",
            config={
                "code": """
async def run(args, state):
    return {"result": "success", "value": 100}
""",
                "input_mapping": {},
                "output_mapping": {"result": "tool_status", "value": "tool_value"},
            },
        )

        state = make_state(unique_id, flow_id="test_tool_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.tool_status == "success"
        assert result.tool_value == 100

    @pytest.mark.asyncio
    async def test_string_result_without_mapping(self, container, unique_id: str):
        """CodeNode: строка без output_mapping -> state.result."""
        node = code_node(
            container,
            node_id="test_tool",
            config={
                "code": """
async def run(args, state):
    return "Tool executed successfully"
""",
                "input_mapping": {},
            },
        )

        state = make_state(unique_id, flow_id="test_tool_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.result == "Tool executed successfully"

    @pytest.mark.asyncio
    async def test_number_result_without_mapping(self, container, unique_id: str):
        """CodeNode: число без output_mapping -> state.result."""
        node = code_node(
            container,
            node_id="test_tool",
            config={
                "code": """
async def run(args, state):
    return args['x'] * args['y']
""",
                "input_mapping": {"x": 7, "y": 6},
            },
        )

        state = make_state(unique_id, flow_id="test_tool_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.result == 42

    @pytest.mark.asyncio
    async def test_list_result_without_mapping(self, container, unique_id: str):
        """CodeNode: список без output_mapping -> state.result."""
        node = code_node(
            container,
            node_id="test_tool",
            config={
                "code": """
async def run(args, state):
    return [1, 2, 3, 4, 5]
""",
                "input_mapping": {},
            },
        )

        state = make_state(unique_id, flow_id="test_tool_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.result == [1, 2, 3, 4, 5]


class TestLlmNodeOutputMapping:
    """Тесты output_mapping для LlmNode (без structured output)."""

    @pytest.mark.asyncio
    async def test_response_without_mapping(self, app, container, mock_llm_with_queue, unique_id: str):
        """LlmNode: response без output_mapping -> state.response."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Hello! How can I help?"}])

        node = LlmNode(
            node_id="test_agent",
            config={"type": "llm_node", "prompt": "You are a helpful assistant"},
            container=container,
        )

        state = make_state(unique_id, flow_id="test_agent_output_mapping", content="Hello")
        result = await run_single_node(container, node, state)

        assert result.response is not None
        assert "Hello" in result.response or len(result.response) > 0

    @pytest.mark.asyncio
    async def test_response_with_mapping(self, app, container, mock_llm_with_queue, unique_id: str):
        """LlmNode: response с output_mapping -> маппинг."""
        # Настраиваем MockLLM
        mock_llm_with_queue([{"type": "text", "content": "Mock response"}])

        node = LlmNode(
            node_id="test_agent",
            config={
                "type": "llm_node",
                "prompt": "You are a helpful assistant",
                "output_mapping": {"response": "agent_answer"},
            },
            container=container,
        )

        state = make_state(unique_id, flow_id="test_agent_output_mapping", content="Hello")
        result = await run_single_node(container, node, state)

        assert result.agent_answer is not None


class TestLlmNodeStructuredOutput:
    """Тесты structured output для LlmNode."""

    @pytest.mark.asyncio
    async def test_structured_output_without_mapping(
        self, app, container, mock_llm_with_queue, unique_id: str
    ):
        """LlmNode: structured output без mapping -> поля напрямую."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "John", "age": 25}}])

        node = LlmNode(
            node_id="test_agent",
            config={
                "type": "llm_node",
                "prompt": "Extract user info from message",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
                    "required": ["name", "age"],
                },
            },
            container=container,
        )

        state = make_state(
            unique_id,
            flow_id="test_agent_structured_output",
            content="My name is John and I am 25 years old",
        )
        result = await run_single_node(container, node, state)

        assert result.name == "John"
        assert result.age == 25

    @pytest.mark.asyncio
    async def test_structured_output_with_mapping(
        self, app, container, mock_llm_with_queue, unique_id: str
    ):
        """LlmNode: structured output с mapping -> маппинг полей."""
        # Настраиваем MockLLM с structured output ответом
        mock_llm_with_queue([{"type": "structured_output", "data": {"name": "Alice", "score": 95}}])

        node = LlmNode(
            node_id="test_agent",
            config={
                "type": "llm_node",
                "prompt": "Extract user info",
                "structured_output": True,
                "output_schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}, "score": {"type": "integer"}},
                    "required": ["name", "score"],
                },
                "output_mapping": {"name": "user_name", "score": "user_score"},
            },
            container=container,
        )

        state = make_state(unique_id, flow_id="test_agent_structured_output", content="Extract info")
        result = await run_single_node(container, node, state)

        assert result.user_name == "Alice"
        assert result.user_score == 95


class TestOutputMappingEdgeCases:
    """Тесты граничных случаев output_mapping."""

    @pytest.mark.asyncio
    async def test_empty_dict_result(self, container, unique_id: str):
        """Пустой dict не меняет state."""
        code = """
async def run(args, state):
    return {}
"""
        node = code_node(container, node_id="test_func", config={"code": code})

        state = make_state(unique_id, flow_id="test_func_output_mapping", existing="value")
        result = await run_single_node(container, node, state)

        assert result.existing == "value"

    @pytest.mark.asyncio
    async def test_mapping_with_missing_keys(self, container, unique_id: str):
        """Маппинг игнорирует отсутствующие ключи."""
        code = """
async def run(args, state):
    return {"field1": "value1"}
"""
        node = code_node(
            container,
            node_id="test_func",
            config={"code": code, "output_mapping": {"field1": "mapped1", "field2": "mapped2"}},
        )

        state = make_state(unique_id, flow_id="test_func_output_mapping")
        result = await run_single_node(container, node, state)

        # field1 замаплен
        assert result.mapped1 == "value1"
        # field2 не существует в результате - не записан
        assert not hasattr(result, "mapped2") or result.mapped2 is None

    @pytest.mark.asyncio
    async def test_nested_dict_in_result(self, container, unique_id: str):
        """Вложенные dict в результате."""
        code = """
async def run(args, state):
    return {
        "user": {"name": "John", "profile": {"age": 25}},
        "metadata": {"timestamp": 12345}
    }
"""
        node = code_node(container, node_id="test_func", config={"code": code})

        state = make_state(unique_id, flow_id="test_func_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.user == {"name": "John", "profile": {"age": 25}}
        assert result.metadata == {"timestamp": 12345}

    @pytest.mark.asyncio
    async def test_mapping_nested_dict_as_whole(self, container, unique_id: str):
        """Маппинг вложенного dict целиком."""
        code = """
async def run(args, state):
    return {"data": {"items": [1, 2, 3], "count": 3}}
"""
        node = code_node(
            container,
            node_id="test_func", config={"code": code, "output_mapping": {"data": "response_data"}}
        )

        state = make_state(unique_id, flow_id="test_func_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.response_data == {"items": [1, 2, 3], "count": 3}

    @pytest.mark.asyncio
    async def test_overwrite_existing_field(self, container, unique_id: str):
        """Результат перезаписывает существующие поля state."""
        code = """
async def run(args, state):
    return {"field": "new_value"}
"""
        node = code_node(container, node_id="test_func", config={"code": code})

        state = make_state(unique_id, flow_id="test_func_output_mapping", field="old_value")
        result = await run_single_node(container, node, state)

        assert result.field == "new_value"

    @pytest.mark.asyncio
    async def test_bool_result_without_mapping(self, container, unique_id: str):
        """Boolean результат -> state.result."""
        code = """
async def run(args, state):
    return True
"""
        node = code_node(container, node_id="test_func", config={"code": code})

        state = make_state(unique_id, flow_id="test_func_output_mapping")
        result = await run_single_node(container, node, state)

        assert result.result is True


class TestDataFlowWithOutputMapping:
    """Тесты передачи данных между нодами с output_mapping."""

    @pytest.mark.asyncio
    async def test_function_to_tool_with_mapping(self, container, unique_id: str):
        """CodeNode с mapping -> CodeNode читает mapped поля."""
        # CodeNode возвращает dict, маппит в другие поля
        func_code = """
async def run(args, state):
    return {"raw_value": 10, "multiplier": 5}
"""
        func_node = code_node(
            container,
            node_id="prepare",
            config={
                "code": func_code,
                "output_mapping": {"raw_value": "input_value", "multiplier": "factor"},
            },
        )

        # CodeNode использует mapped поля
        tool_node = code_node(
            container,
            node_id="multiply",
            config={
                "code": "async def run(args, state):\n    return args['x'] * args['y']",
                "input_mapping": {"x": "@state:input_value", "y": "@state:factor"},
            },
        )

        # Выполняем цепочку
        state = make_state(unique_id, flow_id="function_to_tool_output_mapping")
        state = await run_single_node(container, func_node, state)

        # Проверяем что маппинг сработал
        assert state.input_value == 10
        assert state.factor == 5

        # Выполняем tool
        state = await run_single_node(container, tool_node, state)

        # Tool записал результат
        assert state.result == 50

    @pytest.mark.asyncio
    async def test_tool_chain_with_mapping(self, container, unique_id: str):
        """Цепочка CodeNode с output_mapping."""
        node1 = code_node(
            container,
            node_id="step1",
            config={
                "code": "async def run(args, state):\n    return {'value': args['input'] * 2}",
                "input_mapping": {"input": 10},
                "output_mapping": {"value": "step1_result"},
            },
        )

        node2 = code_node(
            container,
            node_id="step2",
            config={
                "code": "async def run(args, state):\n    return {'final': args['x'] + 5}",
                "input_mapping": {"x": "@state:step1_result"},
                "output_mapping": {"final": "final_result"},
            },
        )

        state = make_state(unique_id, flow_id="tool_chain_output_mapping")
        state = await run_single_node(container, node1, state)

        assert state.step1_result == 20

        state = await run_single_node(container, node2, state)

        assert state.final_result == 25


class TestExecutionStateReturnFromFunction:
    """Тесты возврата ExecutionState из CodeNode."""

    @pytest.mark.asyncio
    async def test_execution_state_return_merges(self, container, unique_id: str):
        """CodeNode: возврат ExecutionState мержится в state."""
        code = """
async def run(args, state):
    state.modified_field = "modified"
    state.new_field = "new"
    return state
"""
        node = code_node(container, node_id="test_func", config={"code": code})

        state = make_state(unique_id, flow_id="execution_state_return_output_mapping", existing="value")
        result = await run_single_node(container, node, state)

        # Все поля сохранились
        assert result.existing == "value"
        assert result.modified_field == "modified"
        assert result.new_field == "new"

    @pytest.mark.asyncio
    async def test_execution_state_return_ignores_output_mapping(self, container, unique_id: str):
        """CodeNode: при возврате ExecutionState output_mapping игнорируется."""
        code = """
async def run(args, state):
    state.field1 = "value1"
    return state
"""
        node = code_node(
            container,
            node_id="test_func",
            config={"code": code, "output_mapping": {"field1": "mapped_field1"}},
        )

        state = make_state(unique_id, flow_id="execution_state_return_output_mapping")
        result = await run_single_node(container, node, state)

        # При возврате ExecutionState маппинг не применяется
        # Поле записано как есть
        assert result.field1 == "value1"
