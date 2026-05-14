"""
Интеграционные тесты для унифицированных контрактов нод.

БЕЗ МОКОВ (кроме LLM согласно правилам проекта).

Тестирует:
- output_mapping: маппинг результата в state
- save_to_messages: добавление результата в messages
- message_field: выбор поля для записи в messages
- diff стейта при save_to_messages без message_field
- передача данных между всеми типами нод
"""

import pytest

from apps.flows.src.models import Edge
from apps.flows.src.runtime import Flow
from apps.flows.src.runtime.nodes import (
    CodeNode,
)
from apps.flows.src.tools.base import CodeTool
from core.state import ExecutionState


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
        "messages": [],
    }
    defaults.update(kwargs)
    return ExecutionState(**defaults)


class TestOutputMapping:
    """Тесты output_mapping для разных типов нод."""

    @pytest.mark.asyncio
    async def test_function_node_returns_dict(self):
        """CodeNode возвращает dict - поля пишутся в state."""
        code = """
async def run(state):
    return {"response": "function_result", "status": "ok"}
"""
        node = CodeNode(node_id="my_function", config={"code": code})

        state = make_state()
        result = await node.run(state)

        assert result.response == "function_result"
        assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_function_node_with_output_mapping(self):
        """CodeNode с output_mapping маппит поля."""
        code = """
async def run(state):
    return {"value": 42, "name": "test"}
"""
        node = CodeNode(
            node_id="my_function",
            config={"code": code, "output_mapping": {"value": "custom_value", "name": "custom_name"}}
        )

        state = make_state()
        result = await node.run(state)

        assert result.custom_value == 42
        assert result.custom_name == "test"

    @pytest.mark.asyncio
    async def test_tool_node_returns_dict(self):
        """CodeNode возвращает dict - поля пишутся в state."""
        node = CodeNode(
            node_id="double_tool",
            config={
                "code": "async def execute(args, state):\n    return {'doubled': args['x'] * 2}",
                "input_mapping": {"x": 10},
            },
        )

        state = make_state()
        result = await node.run(state)

        assert result.doubled == 20

    @pytest.mark.asyncio
    async def test_tool_node_with_output_mapping(self):
        """CodeNode с output_mapping маппит поля."""
        node = CodeNode(
            node_id="triple_tool",
            config={
                "code": "async def execute(args, state):\n    return {'value': args['x'] * 3}",
                "input_mapping": {"x": 10},
                "output_mapping": {"value": "tripled_value"},
            },
        )

        state = make_state()
        result = await node.run(state)

        assert result.tripled_value == 30


class TestSaveToMessages:
    """Тесты save_to_messages."""

    @pytest.mark.asyncio
    async def test_function_node_save_to_messages_disabled(self):
        """CodeNode без save_to_messages не добавляет в messages."""
        code = """
async def run(state):
    state.result = "some_value"
    return state
"""
        node = CodeNode(
            node_id="no_messages",
            config={"code": code, "save_to_messages": False}
        )

        state = make_state(messages=[])
        result = await node.run(state)

        assert len(result.messages) == 0

    @pytest.mark.asyncio
    async def test_function_node_save_to_messages_with_diff(self):
        """CodeNode с save_to_messages добавляет diff стейта."""
        code = """
async def run(state):
    state.new_field = "new_value"
    state.another_field = 123
    return state
"""
        node = CodeNode(
            node_id="with_messages",
            config={"code": code, "save_to_messages": True}
        )

        state = make_state(messages=[])
        result = await node.run(state)

        # Должен быть 1 message с diff стейта
        assert len(result.messages) == 1
        message = result.messages[0]

        # Message содержит diff (новые поля)
        assert "new_field" in str(message) or "new_value" in str(message)

    @pytest.mark.asyncio
    async def test_tool_node_save_to_messages_disabled(self):
        """CodeNode без save_to_messages не добавляет в messages."""
        node = CodeNode(
            node_id="no_msg_tool",
            config={
                "code": "async def execute(args, state):\n    return 42",
                "input_mapping": {},
                "save_to_messages": False,
            },
        )

        state = make_state(messages=[])
        result = await node.run(state)

        assert len(result.messages) == 0

    @pytest.mark.asyncio
    async def test_tool_node_save_to_messages_with_result(self):
        """CodeNode с save_to_messages добавляет результат."""
        node = CodeNode(
            node_id="msg_tool",
            config={
                "code": "async def execute(args, state):\n    return {'answer': 42, 'status': 'ok'}",
                "input_mapping": {},
                "save_to_messages": True,
            },
        )

        state = make_state(messages=[])
        result = await node.run(state)

        assert len(result.messages) == 1


class TestMessageField:
    """Тесты message_field."""

    @pytest.mark.asyncio
    async def test_tool_node_message_field(self):
        """CodeNode с message_field пишет конкретное поле."""
        node = CodeNode(
            node_id="field_tool",
            config={
                "code": "async def execute(args, state):\n    return {'answer': 42, 'debug': 'internal_info'}",
                "input_mapping": {},
                "save_to_messages": True,
                "message_field": "answer",
            },
        )

        state = make_state(messages=[])
        result = await node.run(state)

        assert len(result.messages) == 1
        message = result.messages[0]

        # Должен содержать только answer, не debug
        content = str(message.content) if hasattr(message, 'content') else str(message)
        assert "42" in content
        # debug не должен попасть в message
        assert "internal_info" not in content

    @pytest.mark.asyncio
    async def test_function_node_message_field(self):
        """CodeNode с message_field."""
        code = """
async def run(state):
    state.result = "public_info"
    state.internal = "private_info"
    return state
"""
        node = CodeNode(
            node_id="field_func",
            config={
                "code": code,
                "save_to_messages": True,
                "message_field": "result"
            }
        )

        state = make_state(messages=[])
        result = await node.run(state)

        assert len(result.messages) == 1
        message = result.messages[0]
        content = str(message.content) if hasattr(message, 'content') else str(message)
        assert "public_info" in content


class TestStateDiff:
    """Тесты diff стейта при save_to_messages."""

    @pytest.mark.asyncio
    async def test_diff_only_new_fields(self):
        """Diff содержит только новые поля."""
        code = """
async def run(state):
    state.new_field1 = "value1"
    state.new_field2 = "value2"
    return state
"""
        node = CodeNode(
            node_id="diff_test",
            config={"code": code, "save_to_messages": True}
        )

        state = make_state(
            messages=[],
            existing_field="should_not_appear"
        )
        result = await node.run(state)

        assert len(result.messages) == 1
        message = result.messages[0]
        content = str(message.content) if hasattr(message, 'content') else str(message)

        # Новые поля должны быть в diff
        assert "new_field1" in content or "value1" in content
        # Существующие поля не должны быть в diff
        assert "existing_field" not in content

    @pytest.mark.asyncio
    async def test_diff_changed_fields(self):
        """Diff содержит измененные поля."""
        code = """
async def run(state):
    state.mutable_field = "changed_value"
    return state
"""
        node = CodeNode(
            node_id="change_test",
            config={"code": code, "save_to_messages": True}
        )

        state = make_state(
            messages=[],
            mutable_field="original_value"
        )
        result = await node.run(state)

        assert len(result.messages) == 1
        message = result.messages[0]
        content = str(message.content) if hasattr(message, 'content') else str(message)

        # Измененное значение должно быть в diff
        assert "changed_value" in content


class TestAllNodeTypesDataFlow:
    """Тесты передачи данных между всеми типами нод."""

    @pytest.mark.asyncio
    async def test_function_to_tool_data_flow(self):
        """CodeNode -> CodeNode: передача данных."""
        func_code = """
async def run(state):
    state.calculated_value = 100
    state.factor = 5
    return state
"""
        func_node = CodeNode(node_id="prepare", config={"code": func_code})

        tool_node = CodeNode(
            node_id="multiply",
            config={
                "code": "async def execute(args, state):\n    return {'result': args['value'] * args['multiplier']}",
                "input_mapping": {
                    "value": "@state:calculated_value",
                    "multiplier": "@state:factor"
                }
            },
        )

        flow = Flow(
            flow_id="func_to_tool",
            name="Function to Tool Agent",
            entry="prepare",
            nodes={"prepare": func_node, "multiply": tool_node},
            edges=[
                Edge(from_node="prepare", to_node="multiply"),
                Edge(from_node="multiply", to_node=None),
            ],
            variables={},
        )

        state = make_state()
        result = await flow.run(state)

        assert result.calculated_value == 100
        assert result.factor == 5
        assert result.result == 500

    @pytest.mark.asyncio
    async def test_tool_to_function_data_flow(self):
        """CodeNode -> CodeNode: передача данных."""
        tool_node = CodeNode(
            node_id="generate",
            config={
                "code": "async def execute(args, state):\n    return {'generated_item': {'id': 12345, 'name': 'Test Item'}}",
                "input_mapping": {},
            },
        )

        func_code = """
async def run(state):
    item = state.generated_item
    state.formatted = f"Item #{item['id']}: {item['name']}"
    return state
"""
        func_node = CodeNode(node_id="format", config={"code": func_code})

        flow = Flow(
            flow_id="tool_to_func",
            name="Tool to Function Agent",
            entry="generate",
            nodes={"generate": tool_node, "format": func_node},
            edges=[
                Edge(from_node="generate", to_node="format"),
                Edge(from_node="format", to_node=None),
            ],
            variables={},
        )

        state = make_state()
        result = await flow.run(state)

        assert result.generated_item == {'id': 12345, 'name': 'Test Item'}
        assert result.formatted == "Item #12345: Test Item"

    @pytest.mark.asyncio
    async def test_tool_chain_data_flow(self):
        """Цепочка CodeNode: каждый читает результат предыдущего."""
        node1 = CodeNode(
            node_id="add_ten",
            config={
                "code": "async def execute(args, state):\n    return {'after_add': args['x'] + 10}",
                "input_mapping": {"x": "@state:initial"},
            },
        )
        node2 = CodeNode(
            node_id="double",
            config={
                "code": "async def execute(args, state):\n    return {'after_double': args['x'] * 2}",
                "input_mapping": {"x": "@state:after_add"},
            },
        )
        node3 = CodeNode(
            node_id="subtract",
            config={
                "code": "async def execute(args, state):\n    return {'final': args['x'] - 5}",
                "input_mapping": {"x": "@state:after_double"},
            },
        )

        flow = Flow(
            flow_id="tool_chain",
            name="Tool Chain Agent",
            entry="add_ten",
            nodes={
                "add_ten": node1,
                "double": node2,
                "subtract": node3,
            },
            edges=[
                Edge(from_node="add_ten", to_node="double"),
                Edge(from_node="double", to_node="subtract"),
                Edge(from_node="subtract", to_node=None),
            ],
            variables={},
        )

        # initial=5 -> +10=15 -> *2=30 -> -5=25
        state = make_state(initial=5)
        result = await flow.run(state)

        assert result.after_add == 15
        assert result.after_double == 30
        assert result.final == 25

    @pytest.mark.asyncio
    async def test_function_chain_data_flow(self):
        """Цепочка CodeNode: каждый модифицирует state."""
        code1 = """
async def run(state):
    state.step1_done = True
    state.counter = 1
    return state
"""
        code2 = """
async def run(state):
    state.step2_done = True
    state.counter = state.counter + 1
    return state
"""
        code3 = """
async def run(state):
    state.step3_done = True
    state.counter = state.counter + 1
    state.summary = f"Steps completed: {state.counter}"
    return state
"""
        node1 = CodeNode(node_id="step1", config={"code": code1})
        node2 = CodeNode(node_id="step2", config={"code": code2})
        node3 = CodeNode(node_id="step3", config={"code": code3})

        flow = Flow(
            flow_id="func_chain",
            name="Function Chain Agent",
            entry="step1",
            nodes={"step1": node1, "step2": node2, "step3": node3},
            edges=[
                Edge(from_node="step1", to_node="step2"),
                Edge(from_node="step2", to_node="step3"),
                Edge(from_node="step3", to_node=None),
            ],
            variables={},
        )

        state = make_state()
        result = await flow.run(state)

        assert result.step1_done is True
        assert result.step2_done is True
        assert result.step3_done is True
        assert result.counter == 3
        assert result.summary == "Steps completed: 3"

    @pytest.mark.asyncio
    async def test_mixed_nodes_with_messages(self):
        """Смешанная цепочка с save_to_messages."""
        func_code = """
async def run(state):
    state.user_data = {"name": "Alice", "score": 100}
    return state
"""
        func_node = CodeNode(
            node_id="init",
            config={"code": func_code, "save_to_messages": True}
        )

        tool_node = CodeNode(
            node_id="add_bonus",
            config={
                "code": "async def execute(args, state):\n    return {'final_score': args['score'] + args['bonus']}",
                "input_mapping": {
                    "score": "@state:user_data.score",
                    "bonus": "@var:bonus_amount"
                },
                "save_to_messages": True
            }
        )

        flow = Flow(
            flow_id="mixed_messages",
            name="Mixed with Messages Agent",
            entry="init",
            nodes={"init": func_node, "add_bonus": tool_node},
            edges=[
                Edge(from_node="init", to_node="add_bonus"),
                Edge(from_node="add_bonus", to_node=None),
            ],
            variables={"bonus_amount": 50},
        )

        state = make_state(messages=[])
        result = await flow.run(state)

        assert result.user_data == {"name": "Alice", "score": 100}
        assert result.final_score == 150
        # Оба узла должны добавить messages
        assert len(result.messages) == 2


class TestFromConfig:
    """Тесты создания нод из конфигурации."""

    @pytest.mark.asyncio
    async def test_flow_from_config_with_output_mapping(self):
        """Agent из конфига с output_mapping."""
        flow_config = {
            "id": "config_test",
            "name": "Config Test Agent",
            "entry": "step1",
            "nodes": {
                "step1": {
                    "type": "code",
                    "code": "async def execute(args, state):\n    return {'result': 'step1_result'}",
                    "output_mapping": {"result": "first_result"},
                },
                "step2": {
                    "type": "code",
                    "code": """
async def run(state):
    state.combined = f"Got: {state.first_result}"
    return state
""",
                },
            },
            "edges": [
                {"from": "step1", "to": "step2"},
                {"from": "step2", "to": None},
            ],
        }

        flow = await Flow.from_config(flow_config)
        state = make_state()
        result = await flow.run(state)

        assert result.first_result == "step1_result"
        assert result.combined == "Got: step1_result"

    @pytest.mark.asyncio
    async def test_flow_from_config_with_save_to_messages(self):
        """Agent из конфига с save_to_messages."""
        flow_config = {
            "id": "messages_test",
            "name": "Messages Test Agent",
            "entry": "process",
            "nodes": {
                "process": {
                    "type": "code",
                    "code": "async def execute(args, state):\n    return {'status': 'ok', 'data': 123}",
                    "save_to_messages": True,
                },
            },
            "edges": [
                {"from": "process", "to": None},
            ],
        }

        flow = await Flow.from_config(flow_config)
        state = make_state(messages=[])
        result = await flow.run(state)

        assert result.status == "ok"
        assert result.data == 123
        assert len(result.messages) == 1

    @pytest.mark.asyncio
    async def test_flow_from_config_with_message_field(self):
        """Agent из конфига с message_field."""
        flow_config = {
            "id": "field_test",
            "name": "Field Test Agent",
            "entry": "process",
            "nodes": {
                "process": {
                    "type": "code",
                    "code": "async def execute(args, state):\n    return {'public': 'show this', 'private': 'hide this'}",
                    "save_to_messages": True,
                    "message_field": "public",
                },
            },
            "edges": [
                {"from": "process", "to": None},
            ],
        }

        flow = await Flow.from_config(flow_config)
        state = make_state(messages=[])
        result = await flow.run(state)

        assert len(result.messages) == 1
        message = result.messages[0]
        content = str(message.content) if hasattr(message, 'content') else str(message)
        assert "show this" in content
        assert "hide this" not in content


class TestComplexPipeline:
    """Тесты комплексного pipeline со всеми типами нод."""

    @pytest.mark.asyncio
    async def test_etl_pipeline(self):
        """
        ETL Pipeline: Extract -> Transform -> Load.

        1. Extract (CodeNode): извлекает данные
        2. Transform (CodeNode): трансформирует
        3. Load (CodeNode): сохраняет с save_to_messages
        """
        CodeTool(
            tool_id="extract",
            code="""
async def execute(args, state):
    return {
        'extracted': {
            'items': [
                {'id': 1, 'name': 'item1', 'price': 100},
                {'id': 2, 'name': 'item2', 'price': 200},
            ],
            'total': 2
        }
    }
""",
        )

        CodeTool(
            tool_id="load",
            code="""
async def execute(args, state):
    return {
        'load_result': {
            'saved': len(args['items']),
            'total_value': args['total_price']
        }
    }
""",
        )

        transform_code = """
async def run(state):
    items = state.extracted['items']
    # Увеличиваем цены на 10%
    transformed = [
        {**item, 'price': int(item['price'] * 1.1)}
        for item in items
    ]
    state.transformed_items = transformed
    state.total_price = sum(item['price'] for item in transformed)
    return state
"""

        extract_node = CodeNode(
            node_id="extract",
            config={
                "code": """
async def execute(args, state):
    return {
        'extracted': {
            'items': [
                {'id': 1, 'name': 'item1', 'price': 100},
                {'id': 2, 'name': 'item2', 'price': 200},
            ],
            'total': 2
        }
    }
""",
                "input_mapping": {},
            },
        )

        transform_node = CodeNode(
            node_id="transform",
            config={"code": transform_code, "save_to_messages": True}
        )

        load_node = CodeNode(
            node_id="load",
            config={
                "code": """
async def execute(args, state):
    return {
        'load_result': {
            'saved': len(args['items']),
            'total_value': args['total_price']
        }
    }
""",
                "input_mapping": {
                    "items": "@state:transformed_items",
                    "total_price": "@state:total_price"
                },
                "save_to_messages": True
            }
        )

        flow = Flow(
            flow_id="etl_pipeline",
            name="ETL Pipeline Agent",
            entry="extract",
            nodes={
                "extract": extract_node,
                "transform": transform_node,
                "load": load_node,
            },
            edges=[
                Edge(from_node="extract", to_node="transform"),
                Edge(from_node="transform", to_node="load"),
                Edge(from_node="load", to_node=None),
            ],
            variables={},
        )

        state = make_state(messages=[])
        result = await flow.run(state)

        # Extract results
        assert result.extracted['total'] == 2

        # Transform results (10% increase: 100->110, 200->220)
        assert len(result.transformed_items) == 2
        assert result.transformed_items[0]['price'] == 110
        assert result.transformed_items[1]['price'] == 220
        assert result.total_price == 330

        # Load results
        assert result.load_result['saved'] == 2
        assert result.load_result['total_value'] == 330

        # Messages (transform и load)
        assert len(result.messages) == 2

    @pytest.mark.asyncio
    async def test_conditional_pipeline_with_all_features(self):
        """
        Условный pipeline со всеми фичами.

        1. Classify (CodeNode): определяет тип запроса
        2. Route (conditional): к process_a или process_b
        3. Process (CodeNode): обрабатывает с save_to_messages
        4. Finalize (CodeNode): финализирует
        """
        classify_code = """
async def run(state):
    content = state.content or ""
    state.is_urgent = "urgent" in content.lower()
    state.request_type = "urgent" if state.is_urgent else "normal"
    return state
"""

        CodeTool(
            tool_id="urgent_handler",
            code="""
async def execute(args, state):
    return {
        'process_result': {
            'priority': 'HIGH',
            'handler': 'urgent_team',
            'message': f'Urgent: {args["content"]}'
        }
    }
""",
        )

        CodeTool(
            tool_id="normal_handler",
            code="""
async def execute(args, state):
    return {
        'process_result': {
            'priority': 'NORMAL',
            'handler': 'standard_queue',
            'message': f'Request: {args["content"]}'
        }
    }
""",
        )

        finalize_code = """
async def run(state):
    result = state.process_result
    state.response = f"Processed by {result['handler']}: {result['message']}"
    return state
"""

        classify_node = CodeNode(
            node_id="classify",
            config={"code": classify_code, "save_to_messages": True}
        )

        urgent_node = CodeNode(
            node_id="urgent_process",
            config={
                "code": """
async def execute(args, state):
    return {
        'process_result': {
            'priority': 'HIGH',
            'handler': 'urgent_team',
            'message': f'Urgent: {args["content"]}'
        }
    }
""",
                "input_mapping": {"content": "@state:content"},
                "save_to_messages": True,
                "message_field": "priority"
            }
        )

        normal_node = CodeNode(
            node_id="normal_process",
            config={
                "code": """
async def execute(args, state):
    return {
        'process_result': {
            'priority': 'NORMAL',
            'handler': 'standard_queue',
            'message': f'Request: {args["content"]}'
        }
    }
""",
                "input_mapping": {"content": "@state:content"},
                "save_to_messages": True,
                "message_field": "priority"
            }
        )

        finalize_node = CodeNode(
            node_id="finalize",
            config={"code": finalize_code, "save_to_messages": True, "message_field": "response"}
        )

        flow = Flow(
            flow_id="conditional_pipeline",
            name="Conditional Pipeline Agent",
            entry="classify",
            nodes={
                "classify": classify_node,
                "urgent_process": urgent_node,
                "normal_process": normal_node,
                "finalize": finalize_node,
            },
            edges=[
                Edge(from_node="classify", to_node="urgent_process", condition="is_urgent == true"),
                Edge(from_node="classify", to_node="normal_process", condition="is_urgent == false"),
                Edge(from_node="urgent_process", to_node="finalize"),
                Edge(from_node="normal_process", to_node="finalize"),
                Edge(from_node="finalize", to_node=None),
            ],
            variables={},
        )

        # Тест urgent
        state1 = make_state(content="URGENT: Fix critical bug", messages=[])
        result1 = await flow.run(state1)

        assert result1.is_urgent is True
        assert result1.request_type == "urgent"
        assert result1.process_result['priority'] == "HIGH"
        assert "urgent_team" in result1.response

        # Тест normal
        state2 = make_state(content="Please help with configuration", messages=[])
        result2 = await flow.run(state2)

        assert result2.is_urgent is False
        assert result2.request_type == "normal"
        assert result2.process_result['priority'] == "NORMAL"
        assert "standard_queue" in result2.response
