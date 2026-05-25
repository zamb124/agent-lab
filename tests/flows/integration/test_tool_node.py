"""
Интеграционные тесты для CodeNode.

Тестирует CodeNode в контексте Agent с реальными tools.
"""

import pytest

from apps.flows.src.models import Edge
from apps.flows.src.runtime.flow import Flow
from apps.flows.src.runtime.nodes import CodeNode, create_node
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_flow, run_node, workflow_state


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    defaults.update(kwargs)
    if "context_id" in kwargs and "session_id" not in kwargs:
        defaults["session_id"] = f"test-agent:{kwargs['context_id']}"
    return ExecutionState(**defaults)


class TestCodeNodeInAgent:
    """Тесты CodeNode в контексте Agent."""

    @pytest.mark.asyncio
    async def test_flow_with_inline_tool_node(self, container, unique_id):
        """Agent с inline CodeNode."""
        prepare_code = "\nasync def run(args, state):\n    state.value = 10\n    state.multiplier = 3\n    return state\n"
        prepare_node = CodeNode(
            node_id="prepare",
            config={"type": "code", "code": prepare_code},
            container=container,
        )
        multiply_code = (
            "\nasync def run(args, state):\n    return {'result': args['x'] * args['factor']}\n"
        )
        tool_node = CodeNode(
            node_id="multiply",
            config={
                "type": "code",
                "code": multiply_code,
                "input_mapping": {"x": "@state:value", "factor": "@state:multiplier"},
            },
            container=container,
        )
        format_code = '\nasync def run(args, state):\n    state.response = f"Результат: {state.result}"\n    return state\n'
        format_node = CodeNode(
            node_id="format",
            config={"type": "code", "code": format_code},
            container=container,
        )
        flow = Flow(
            flow_id="test_flow",
            name="Test Agent",
            entry="prepare",
            nodes={"prepare": prepare_node, "multiply": tool_node, "format": format_node},
            edges=[
                Edge(from_node="prepare", to_node="multiply"),
                Edge(from_node="multiply", to_node="format"),
                Edge(from_node="format", to_node=None),
            ],
            variables={},
            container=container,
        )

        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, content="test")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.result == 30
        assert result.response == "Результат: 30"

    @pytest.mark.asyncio
    async def test_flow_with_tool_node_and_variables(self, container, unique_id):
        """Agent с CodeNode и переменными из variables."""
        greet_code = "\nasync def run(args, state):\n    return {'greeting': f\"Добро пожаловать в {args['company']}, {args['name']}!\"}\n"
        tool_node = CodeNode(
            node_id="greet",
            config={
                "type": "code",
                "code": greet_code,
                "input_mapping": {"company": "@var:company_name", "name": "@state:user_name"},
            },
            container=container,
        )
        flow = Flow(
            flow_id="greet_flow",
            name="Greet Agent",
            entry="greet",
            nodes={"greet": tool_node},
            edges=[Edge(from_node="greet", to_node=None)],
            variables={"company_name": "Platform Corp"},
            container=container,
        )
        state = workflow_state(
            flow_id=flow.flow_id,
            unique_id=unique_id,
            user_name="Алексей",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.greeting == "Добро пожаловать в Platform Corp, Алексей!"

    @pytest.mark.asyncio
    async def test_flow_with_conditional_tool_node(self, container, unique_id):
        """Agent с условным переходом к CodeNode."""
        classifier_code = '\nasync def run(args, state):\n    content = state.content or ""\n    state.needs_calc = "=" in content\n    state.expr = content.replace("=", "").strip()\n    return state\n'
        classifier_node = CodeNode(
            node_id="classifier",
            config={"type": "code", "code": classifier_code},
            container=container,
        )
        calc_code = "\nasync def run(args, state):\n    parts = args['expr'].split('+')\n    return {'calc_result': sum(int(p.strip()) for p in parts)}\n"
        calc_node = CodeNode(
            node_id="calculate",
            config={"type": "code", "code": calc_code, "input_mapping": {"expr": "@state:expr"}},
            container=container,
        )
        skip_code = (
            '\nasync def run(args, state):\n    state.calc_result = "N/A"\n    return state\n'
        )
        skip_node = CodeNode(
            node_id="skip",
            config={"type": "code", "code": skip_code},
            container=container,
        )
        flow = Flow(
            flow_id="conditional_flow",
            name="Conditional Agent",
            entry="classifier",
            nodes={"classifier": classifier_node, "calculate": calc_node, "skip": skip_node},
            edges=[
                Edge(
                    from_node="classifier",
                    to_node="calculate",
                    condition={
                        "type": "simple",
                        "variable": "needs_calc",
                        "operator": "==",
                        "value": True,
                    },
                ),
                Edge(
                    from_node="classifier",
                    to_node="skip",
                    condition={
                        "type": "simple",
                        "variable": "needs_calc",
                        "operator": "==",
                        "value": False,
                    },
                ),
                Edge(from_node="calculate", to_node=None),
                Edge(from_node="skip", to_node=None),
            ],
            variables={},
            container=container,
        )
        state1 = workflow_state(
            flow_id=flow.flow_id,
            unique_id=f"{unique_id}-calc",
            content="2 + 3 =",
        )
        result1 = await run_flow(container=container, flow=flow, state=state1)
        assert result1["calc_result"] == 5
        state2 = workflow_state(
            flow_id=flow.flow_id,
            unique_id=f"{unique_id}-skip",
            content="просто текст",
        )
        result2 = await run_flow(container=container, flow=flow, state=state2)
        assert result2["calc_result"] == "N/A"


class TestCodeNodeFromConfig:
    """Тесты создания CodeNode через create_node."""

    @pytest.mark.asyncio
    async def test_create_node_with_inline_code(self, container, unique_id):
        """create_node создает CodeNode из inline кода."""
        config = {
            "type": "code",
            "code": "async def run(args, state):\n    return {'squared': args['a'] ** 2}",
            "parameters_schema": {
                "type": "object",
                "properties": {
                    "a": {"type": "integer", "description": "Число для возведения в квадрат"}
                },
                "required": ["a"],
            },
            "input_mapping": {"a": 7},
        }
        node = await create_node("square_node", config, container=container)
        assert isinstance(node, CodeNode)
        assert node.node_id == "square_node"
        result = await run_node(
            container=container,
            node=node,
            state=workflow_state(flow_id="square_node_flow", unique_id=unique_id),
        )
        assert result.squared == 49

    @pytest.mark.asyncio
    async def test_flow_from_config_with_tool_node(self, container, unique_id):
        """Agent из конфига с CodeNode."""
        flow_config = {
            "flow_id": "config_flow",
            "name": "Config Agent",
            "entry": "prepare",
            "nodes": {
                "prepare": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state.input_value = 5\n    return state",
                },
                "process": {
                    "type": "code",
                    "code": "async def run(args, state):\n    return {'processed': args['x'] * 10}",
                    "input_mapping": {"x": "@state:input_value"},
                },
                "finish": {
                    "type": "code",
                    "code": 'async def run(args, state):\n    state.response = f"Processed: {state.processed}"\n    return state',
                },
            },
            "edges": [
                {"from_node": "prepare", "to_node": "process"},
                {"from_node": "process", "to_node": "finish"},
                {"from_node": "finish", "to_node": None},
            ],
            "variables": {},
        }
        flow = await Flow.from_config(flow_config, container=container)
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, content="start")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result["processed"] == 50
        assert result["response"] == "Processed: 50"


class TestCodeNodeWithSkillVariables:
    """Тесты CodeNode с переменными из skill."""

    @pytest.mark.asyncio
    async def test_tool_node_uses_skill_variables(self, container, unique_id):
        """CodeNode использует переменные из текущего skill."""
        format_code = "\nasync def run(args, state):\n    return {'formatted_id': f\"{args['prefix']}{args['id']}\"}\n"
        tool_node = CodeNode(
            node_id="format",
            config={
                "type": "code",
                "code": format_code,
                "input_mapping": {"prefix": "@var:prefix", "id": "@state:entity_id"},
            },
            container=container,
        )
        flow = Flow(
            flow_id="skill_flow",
            name="Skill Agent",
            entry="format",
            nodes={"format": tool_node},
            edges=[Edge(from_node="format", to_node=None)],
            variables={"prefix": "ORDER-"},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=f"{unique_id}-order", entity_id="12345")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.formatted_id == "ORDER-12345"
        flow.variables = {"prefix": "TICKET-"}
        state2 = workflow_state(flow_id=flow.flow_id, unique_id=f"{unique_id}-ticket", entity_id="67890")
        result2 = await run_flow(container=container, flow=flow, state=state2)
        assert result2.formatted_id == "TICKET-67890"


class TestCodeNodeChaining:
    """Тесты цепочки CodeNode."""

    @pytest.mark.asyncio
    async def test_chain_of_tool_nodes(self, container, unique_id):
        """Цепочка CodeNode передает данные через state."""
        double_code = "\nasync def run(args, state):\n    return {'doubled': args['x'] * 2}\n"
        add_code = "\nasync def run(args, state):\n    return {'final': args['a'] + args['b']}\n"
        node1 = CodeNode(
            node_id="step1",
            config={"type": "code", "code": double_code, "input_mapping": {"x": "@state:input"}},
            container=container,
        )
        node2 = CodeNode(
            node_id="step2",
            config={
                "type": "code",
                "code": add_code,
                "input_mapping": {"a": "@state:doubled", "b": "@var:bonus"},
            },
            container=container,
        )
        flow = Flow(
            flow_id="chain_flow",
            name="Chain Agent",
            entry="step1",
            nodes={"step1": node1, "step2": node2},
            edges=[Edge(from_node="step1", to_node="step2"), Edge(from_node="step2", to_node=None)],
            variables={"bonus": 100},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, input=25)
        result = await run_flow(container=container, flow=flow, state=state)
        assert result["doubled"] == 50
        assert result["final"] == 150


class TestCodeNodeDynamicDataAgent:
    """
    Тесты динамической передачи данных между CodeNode.

    Проверяет что @state:, @var: и константы корректно работают
    в цепочке CodeNode где каждый tool модифицирует state.
    """

    @pytest.mark.asyncio
    async def test_dynamic_state_flow_with_all_mapping_types(self, container, unique_id):
        """
        Цепочка CodeNode с @state:, @var: и константами.
        """
        init_code = "async def run(args, state):\n    return {'base_value': args['initial']}"
        multiply_code = (
            "async def run(args, state):\n    return {'multiplied': args['value'] * args['factor']}"
        )
        add_const_code = (
            "async def run(args, state):\n    return {'added': args['value'] + args['const']}"
        )
        final_code = "async def run(args, state):\n    return {'final_result': args['current'] + args['original'] + args['bonus']}"
        node1 = CodeNode(
            node_id="init_node",
            config={"type": "code", "code": init_code, "input_mapping": {"initial": 10}},
            container=container,
        )
        node2 = CodeNode(
            node_id="multiply_node",
            config={
                "type": "code",
                "code": multiply_code,
                "input_mapping": {"value": "@state:base_value", "factor": "@var:multiplier"},
            },
            container=container,
        )
        node3 = CodeNode(
            node_id="add_node",
            config={
                "type": "code",
                "code": add_const_code,
                "input_mapping": {"value": "@state:multiplied", "const": 50},
            },
            container=container,
        )
        node4 = CodeNode(
            node_id="final_node",
            config={
                "type": "code",
                "code": final_code,
                "input_mapping": {
                    "current": "@state:added",
                    "original": "@state:base_value",
                    "bonus": "@var:bonus",
                },
            },
            container=container,
        )
        flow = Flow(
            flow_id="dynamic_flow",
            name="Dynamic Data Agent",
            entry="init_node",
            nodes={
                "init_node": node1,
                "multiply_node": node2,
                "add_node": node3,
                "final_node": node4,
            },
            edges=[
                Edge(from_node="init_node", to_node="multiply_node"),
                Edge(from_node="multiply_node", to_node="add_node"),
                Edge(from_node="add_node", to_node="final_node"),
                Edge(from_node="final_node", to_node=None),
            ],
            variables={"multiplier": 3, "bonus": 5},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, content="start")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.base_value == 10
        assert result.multiplied == 30
        assert result.added == 80
        assert result.final_result == 95

    @pytest.mark.asyncio
    async def test_dynamic_nested_state_modification(self, container, unique_id):
        """Тест с вложенными структурами в state."""
        setup_code = "async def run(args, state):\n    return {'user': {'data': {'score': args['initial_score'], 'name': args['name']}}}"
        boost_code = "async def run(args, state):\n    return {'boosted_score': args['score'] + args['boost']}"
        format_code = "async def run(args, state):\n    return {'formatted_result': f\"{args['prefix']}{args['name']}: {args['final_score']}\"}"
        node1 = CodeNode(
            node_id="setup_node",
            config={
                "type": "code",
                "code": setup_code,
                "input_mapping": {"initial_score": 100, "name": "@var:player_name"},
            },
            container=container,
        )
        node2 = CodeNode(
            node_id="boost_node",
            config={
                "type": "code",
                "code": boost_code,
                "input_mapping": {"score": "@state:user.data.score", "boost": "@var:boost_amount"},
            },
            container=container,
        )
        node3 = CodeNode(
            node_id="format_node",
            config={
                "type": "code",
                "code": format_code,
                "input_mapping": {
                    "prefix": "Player ",
                    "name": "@state:user.data.name",
                    "final_score": "@state:boosted_score",
                },
            },
            container=container,
        )
        flow = Flow(
            flow_id="nested_flow",
            name="Nested State Agent",
            entry="setup_node",
            nodes={"setup_node": node1, "boost_node": node2, "format_node": node3},
            edges=[
                Edge(from_node="setup_node", to_node="boost_node"),
                Edge(from_node="boost_node", to_node="format_node"),
                Edge(from_node="format_node", to_node=None),
            ],
            variables={"player_name": "Alice", "boost_amount": 50},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, content="start")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.user["data"]["score"] == 100
        assert result.user["data"]["name"] == "Alice"
        assert result.boosted_score == 150
        assert result.formatted_result == "Player Alice: 150"

    @pytest.mark.asyncio
    async def test_tool_modifies_state_for_next_tool(self, container, unique_id):
        """Тест где каждый tool записывает результат который читает следующий."""
        extract_code = "async def run(args, state):\n    return {'extracted_data': {'items': args['raw'].split(','), 'count': len(args['raw'].split(','))}}"
        transform_code = "async def run(args, state):\n    return {'transformed_data': [item.strip().upper() for item in args['data']['items']]}"
        validate_code = "async def run(args, state):\n    return {'is_valid': len(args['items']) >= args['min_count']}"
        save_code = "async def run(args, state):\n    return {'saved_result': {'items': args['items'], 'valid': args['is_valid'], 'source': args['source']}}"
        node1 = CodeNode(
            node_id="extract_node",
            config={"type": "code", "code": extract_code, "input_mapping": {"raw": "@state:raw_input"}},
            container=container,
        )
        node2 = CodeNode(
            node_id="transform_node",
            config={
                "type": "code",
                "code": transform_code,
                "input_mapping": {"data": "@state:extracted_data"},
            },
            container=container,
        )
        node3 = CodeNode(
            node_id="validate_node",
            config={
                "type": "code",
                "code": validate_code,
                "input_mapping": {
                    "items": "@state:transformed_data",
                    "min_count": "@var:min_items",
                },
            },
            container=container,
        )
        node4 = CodeNode(
            node_id="save_node",
            config={
                "type": "code",
                "code": save_code,
                "input_mapping": {
                    "items": "@state:transformed_data",
                    "is_valid": "@state:is_valid",
                    "source": "api",
                },
            },
            container=container,
        )
        flow = Flow(
            flow_id="pipeline_flow",
            name="Data Pipeline Agent",
            entry="extract_node",
            nodes={
                "extract_node": node1,
                "transform_node": node2,
                "validate_node": node3,
                "save_node": node4,
            },
            edges=[
                Edge(from_node="extract_node", to_node="transform_node"),
                Edge(from_node="transform_node", to_node="validate_node"),
                Edge(from_node="validate_node", to_node="save_node"),
                Edge(from_node="save_node", to_node=None),
            ],
            variables={"min_items": 2},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, raw_input="apple, banana, cherry")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result["extracted_data"]["count"] == 3
        assert result["transformed_data"] == ["APPLE", "BANANA", "CHERRY"]
        assert result["is_valid"] is True
        assert result["saved_result"]["items"] == ["APPLE", "BANANA", "CHERRY"]
        assert result["saved_result"]["valid"] is True
        assert result["saved_result"]["source"] == "api"

    @pytest.mark.asyncio
    async def test_mixed_function_and_tool_nodes_data_flow(self, container, unique_id):
        """Тест смешанного flow: CodeNode передают данные друг другу."""
        init_code = "\nasync def run(args, state):\n    state.x_value = 7\n    state.y_value = 8\n    return state\n"
        multiply_code = "async def run(args, state):\n    return {'product': args['x'] * args['y']}"
        process_code = "\nasync def run(args, state):\n    state.processed_value = state.product + 100\n    return state\n"
        finalize_code = "async def run(args, state):\n    return {'final_message': f\"Result: {args['value']} (bonus: {args['bonus']})\"}"
        init_func = CodeNode(
            node_id="init_func",
            config={"type": "code", "code": init_code},
            container=container,
        )
        tool_node1 = CodeNode(
            node_id="multiply_node",
            config={
                "type": "code",
                "code": multiply_code,
                "input_mapping": {"x": "@state:x_value", "y": "@state:y_value"},
            },
            container=container,
        )
        process_func = CodeNode(
            node_id="process_func",
            config={"type": "code", "code": process_code},
            container=container,
        )
        tool_node2 = CodeNode(
            node_id="finalize_node",
            config={
                "type": "code",
                "code": finalize_code,
                "input_mapping": {"value": "@state:processed_value", "bonus": "@var:bonus_text"},
            },
            container=container,
        )
        flow = Flow(
            flow_id="mixed_flow",
            name="Mixed Nodes Agent",
            entry="init_func",
            nodes={
                "init_func": init_func,
                "multiply_node": tool_node1,
                "process_func": process_func,
                "finalize_node": tool_node2,
            },
            edges=[
                Edge(from_node="init_func", to_node="multiply_node"),
                Edge(from_node="multiply_node", to_node="process_func"),
                Edge(from_node="process_func", to_node="finalize_node"),
                Edge(from_node="finalize_node", to_node=None),
            ],
            variables={"bonus_text": "+VIP"},
            container=container,
        )
        state = workflow_state(flow_id=flow.flow_id, unique_id=unique_id, content="start")
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.x_value == 7
        assert result.y_value == 8
        assert result.product == 56
        assert result.processed_value == 156
        assert result.final_message == "Result: 156 (bonus: +VIP)"
