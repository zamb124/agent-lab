"""
Интеграционные тесты для ToolNode.

Тестирует ToolNode в контексте Agent с реальными tools.
"""

import pytest
from apps.agents.src.agent import Agent
from apps.agents.src.agent.nodes import create_node, ToolNode, FunctionNode
from apps.agents.src.models import Edge
from core.state import ExecutionState
from apps.agents.src.tools import InlineTool


def make_state(**kwargs) -> ExecutionState:
    """Создаёт ExecutionState с минимальными обязательными полями."""
    defaults = {
        "task_id": "test-task",
        "context_id": "test-context",
        "user_id": "test-user",
        "session_id": "test-agent:test-context",
    }
    defaults.update(kwargs)
    # Если передан context_id, но не session_id, создаем session_id из context_id
    if "context_id" in kwargs and "session_id" not in kwargs:
        defaults["session_id"] = f"test-agent:{kwargs['context_id']}"
    return ExecutionState(**defaults)


class TestToolNodeInAgent:
    """Тесты ToolNode в контексте Agent."""

    @pytest.mark.asyncio
    async def test_flow_with_inline_tool_node(self):
        """Agent с inline ToolNode."""
        # Создаем inline tool
        inline_tool = InlineTool(
            tool_id="multiplier",
            code="def execute(args, state):\n    return args['x'] * args['factor']",
            description="Умножает число на фактор",
        )

        # Создаем ноды
        def prepare_func(state):
            state.value = 10
            state.multiplier = 3
            return state
        
        prepare_node = FunctionNode(
            node_id="prepare",
            code=prepare_func,
        )

        tool_node = ToolNode(
            node_id="multiply",
            tool=inline_tool,
            input_mapping={
                "x": "@state:value",
                "factor": "@state:multiplier",
            },
            output_key="result",
        )

        def format_func(state):
            state.response = f"Результат: {state.result}"
            return state
        
        format_node = FunctionNode(
            node_id="format",
            code=format_func,
        )

        # Создаем flow
        flow = Agent(
            agent_id="test_flow",
            name="Test Agent",
            entry="prepare",
            nodes={
                "prepare": prepare_node,
                "multiply": tool_node,
                "format": format_node,
            },
            edges=[
                Edge(from_node="prepare", to_node="multiply"),
                Edge(from_node="multiply", to_node="format"),
                Edge(from_node="format", to_node=None),
            ],
            variables={},
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test"
        )
        result = await flow.run(state)

        assert result.result == 30
        assert result.response == "Результат: 30"

    @pytest.mark.asyncio
    async def test_flow_with_tool_node_and_variables(self):
        """Agent с ToolNode и переменными из variables."""
        inline_tool = InlineTool(
            tool_id="greeter",
            code="def execute(args, state):\n    return f\"Добро пожаловать в {args['company']}, {args['name']}!\"",
            description="Приветствие",
        )

        tool_node = ToolNode(
            node_id="greet",
            tool=inline_tool,
            input_mapping={
                "company": "@var:company_name",
                "name": "@state:user_name",
            },
            output_key="greeting",
        )

        flow = Agent(
            agent_id="greet_flow",
            name="Greet Agent",
            entry="greet",
            nodes={"greet": tool_node},
            edges=[Edge(from_node="greet", to_node=None)],
            variables={"company_name": "Platform Corp"},
        )

        from core.state import ExecutionState
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            user_name="Алексей"
        )
        result = await flow.run(state)

        assert result["greeting"] == "Добро пожаловать в Platform Corp, Алексей!"

    @pytest.mark.asyncio
    async def test_flow_with_conditional_tool_node(self):
        """Agent с условным переходом к ToolNode."""
        calc_tool = InlineTool(
            tool_id="calculator",
            code="def execute(args, state):\n    # Простое вычисление без eval\n    parts = args['expr'].split('+')\n    return sum(int(p.strip()) for p in parts)",
            description="Калькулятор",
        )

        def classifier_func(state):
            content = getattr(state, "content", "")
            state.needs_calc = "=" in content
            state.expr = content.replace("=", "").strip()
            return state
        
        classifier_node = FunctionNode(
            node_id="classifier",
            code=classifier_func,
        )

        calc_node = ToolNode(
            node_id="calculate",
            tool=calc_tool,
            input_mapping={"expr": "@state:expr"},
            output_key="calc_result",
        )

        def skip_func(state):
            state.calc_result = "N/A"
            return state
        
        skip_node = FunctionNode(
            node_id="skip",
            code=skip_func,
        )

        flow = Agent(
            agent_id="conditional_flow",
            name="Conditional Agent",
            entry="classifier",
            nodes={
                "classifier": classifier_node,
                "calculate": calc_node,
                "skip": skip_node,
            },
            edges=[
                Edge(from_node="classifier", to_node="calculate", condition="needs_calc == True"),
                Edge(from_node="classifier", to_node="skip", condition="needs_calc == False"),
                Edge(from_node="calculate", to_node=None),
                Edge(from_node="skip", to_node=None),
            ],
            variables={},
        )

        # Тест с вычислением (2 + 3 = 5, без умножения - простой парсер)
        state1 = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="2 + 3 ="
        )
        result1 = await flow.run(state1)
        assert result1["calc_result"] == 5

        # Тест без вычисления
        state2 = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="просто текст"
        )
        result2 = await flow.run(state2)
        assert result2["calc_result"] == "N/A"


class TestToolNodeFromConfig:
    """Тесты создания ToolNode через create_node."""

    @pytest.mark.asyncio
    async def test_create_node_with_inline_code(self):
        """create_node создает ToolNode из inline кода."""
        config = {
            "type": "tool",
            "code": "def execute(args, state):\n    return args['a'] ** 2",
            "args_schema": {
                "a": {"type": "integer", "description": "Число для возведения в квадрат"},
            },
            "input_mapping": {"a": 7},
            "output_key": "squared",
        }

        node = await create_node("square_node", config)

        assert isinstance(node, ToolNode)
        assert node.node_id == "square_node"

        result = await node.run(make_state())
        assert result.model_extra.get("squared") == 49

    @pytest.mark.asyncio
    async def test_flow_from_config_with_tool_node(self):
        """Agent из конфига с ToolNode."""
        # Agent.from_config принимает dict, не AgentConfig
        agent_config = {
            "id": "config_flow",
            "name": "Config Agent",
            "entry": "prepare",
            "nodes": {
                "prepare": {
                    "type": "function",
                    "code": "def run(state):\n    state.input_value = 5\n    return state",
                },
                "process": {
                    "type": "tool",
                    "code": "def execute(args, state):\n    return args['x'] * 10",
                    "input_mapping": {"x": "@state:input_value"},
                    # output_key по умолчанию = "process"
                },
                "finish": {
                    "type": "function",
                    "code": "def run(state):\n    state.response = f\"Processed: {state.process}\"\n    return state",
                },
            },
            "edges": [
                {"from": "prepare", "to": "process"},
                {"from": "process", "to": "finish"},
                {"from": "finish", "to": None},
            ],
            "variables": {},
        }

        flow = await Agent.from_config(agent_config)
        state = make_state(content="start")
        result = await flow.run(state)

        assert result["process"] == 50
        assert result["response"] == "Processed: 50"


class TestToolNodeWithSkillVariables:
    """Тесты ToolNode с переменными из skill."""

    @pytest.mark.asyncio
    async def test_tool_node_uses_skill_variables(self):
        """ToolNode использует переменные из текущего skill."""
        inline_tool = InlineTool(
            tool_id="prefix_formatter",
            code="def execute(args, state):\n    return f\"{args['prefix']}{args['id']}\"",
            description="Форматирует ID с префиксом",
        )

        tool_node = ToolNode(
            node_id="format",
            tool=inline_tool,
            input_mapping={
                "prefix": "@var:prefix",
                "id": "@state:entity_id",
            },
            output_key="formatted_id",
        )

        flow = Agent(
            agent_id="skill_flow",
            name="Skill Agent",
            entry="format",
            nodes={"format": tool_node},
            edges=[Edge(from_node="format", to_node=None)],
            variables={"prefix": "ORDER-"},
        )

        state = make_state(entity_id="12345")
        result = await flow.run(state)

        assert result["formatted_id"] == "ORDER-12345"

        # Теперь с другими переменными (как будто другой skill)
        flow.variables = {"prefix": "TICKET-"}
        state2 = make_state(entity_id="67890")
        result2 = await flow.run(state2)

        assert result2["formatted_id"] == "TICKET-67890"


class TestToolNodeChaining:
    """Тесты цепочки ToolNode."""

    @pytest.mark.asyncio
    async def test_chain_of_tool_nodes(self):
        """Цепочка ToolNode передает данные через state."""
        double_tool = InlineTool(
            tool_id="double",
            code="def execute(args, state):\n    return args['x'] * 2",
        )

        add_tool = InlineTool(
            tool_id="add",
            code="def execute(args, state):\n    return args['a'] + args['b']",
        )

        node1 = ToolNode(
            node_id="step1",
            tool=double_tool,
            input_mapping={"x": "@state:input"},
            output_key="doubled",
        )

        node2 = ToolNode(
            node_id="step2",
            tool=add_tool,
            input_mapping={
                "a": "@state:doubled",
                "b": "@var:bonus",
            },
            output_key="final",
        )

        flow = Agent(
            agent_id="chain_flow",
            name="Chain Agent",
            entry="step1",
            nodes={"step1": node1, "step2": node2},
            edges=[
                Edge(from_node="step1", to_node="step2"),
                Edge(from_node="step2", to_node=None),
            ],
            variables={"bonus": 100},
        )

        state = make_state(input=25)
        result = await flow.run(state)

        assert result["doubled"] == 50
        assert result["final"] == 150


class TestToolNodeDynamicDataAgent:
    """
    Тесты динамической передачи данных между ToolNode.
    
    Проверяет что @state:, @var: и константы корректно работают
    в цепочке ToolNode где каждый tool модифицирует state.
    """

    @pytest.mark.asyncio
    async def test_dynamic_state_flow_with_all_mapping_types(self):
        """
        Цепочка ToolNode с @state:, @var: и константами.
        
        Agent:
        1. init_tool: устанавливает base_value=10 в state
        2. multiply_tool: берет @state:base_value * @var:multiplier, сохраняет в multiplied
        3. add_constant_tool: берет @state:multiplied + константу 50, сохраняет в added
        4. final_tool: берет @state:added + @state:base_value + @var:bonus
        
        Ожидаемый результат:
        - base_value = 10
        - multiplied = 10 * 3 = 30
        - added = 30 + 50 = 80
        - final = 80 + 10 + 5 = 95
        """
        # Tool 1: Инициализирует base_value
        init_tool = InlineTool(
            tool_id="init",
            code="def execute(args, state):\n    return args['initial']",
        )

        # Tool 2: Умножает на multiplier из переменных
        multiply_tool = InlineTool(
            tool_id="multiply",
            code="def execute(args, state):\n    return args['value'] * args['factor']",
        )

        # Tool 3: Добавляет константу
        add_constant_tool = InlineTool(
            tool_id="add_const",
            code="def execute(args, state):\n    return args['value'] + args['const']",
        )

        # Tool 4: Финальный расчет с @state: и @var:
        final_tool = InlineTool(
            tool_id="final_calc",
            code="def execute(args, state):\n    return args['current'] + args['original'] + args['bonus']",
        )

        # Создаем ноды
        node1 = ToolNode(
            node_id="init_node",
            tool=init_tool,
            input_mapping={"initial": 10},  # константа
            output_key="base_value",
        )

        node2 = ToolNode(
            node_id="multiply_node",
            tool=multiply_tool,
            input_mapping={
                "value": "@state:base_value",  # из предыдущего результата
                "factor": "@var:multiplier",   # из переменных flow
            },
            output_key="multiplied",
        )

        node3 = ToolNode(
            node_id="add_node",
            tool=add_constant_tool,
            input_mapping={
                "value": "@state:multiplied",  # из предыдущего результата
                "const": 50,                   # константа
            },
            output_key="added",
        )

        node4 = ToolNode(
            node_id="final_node",
            tool=final_tool,
            input_mapping={
                "current": "@state:added",      # из предыдущего результата
                "original": "@state:base_value", # из первого результата
                "bonus": "@var:bonus",          # из переменных flow
            },
            output_key="final_result",
        )

        flow = Agent(
            agent_id="dynamic_flow",
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
            variables={
                "multiplier": 3,
                "bonus": 5,
            },
        )

        state = make_state(content="start")
        result = await flow.run(state)

        # Проверяем каждый шаг
        assert result["base_value"] == 10, "init_tool должен установить base_value=10"
        assert result["multiplied"] == 30, "multiply_tool: 10 * 3 = 30"
        assert result["added"] == 80, "add_constant_tool: 30 + 50 = 80"
        assert result["final_result"] == 95, "final_tool: 80 + 10 + 5 = 95"

    @pytest.mark.asyncio
    async def test_dynamic_nested_state_modification(self):
        """
        Тест с вложенными структурами в state.
        
        Agent:
        1. setup_tool: создает вложенную структуру user.data.score = 100
        2. boost_tool: берет @state:user.data.score + @var:boost_amount
        3. format_tool: форматирует результат с @state: и константой
        """
        setup_tool = InlineTool(
            tool_id="setup",
            code="""def execute(args, state):
    return {'data': {'score': args['initial_score'], 'name': args['name']}}""",
        )

        boost_tool = InlineTool(
            tool_id="boost",
            code="def execute(args, state):\n    return args['score'] + args['boost']",
        )

        format_tool = InlineTool(
            tool_id="format",
            code="def execute(args, state):\n    return f\"{args['prefix']}{args['name']}: {args['final_score']}\"",
        )

        node1 = ToolNode(
            node_id="setup_node",
            tool=setup_tool,
            input_mapping={
                "initial_score": 100,
                "name": "@var:player_name",
            },
            output_key="user",
        )

        node2 = ToolNode(
            node_id="boost_node",
            tool=boost_tool,
            input_mapping={
                "score": "@state:user.data.score",
                "boost": "@var:boost_amount",
            },
            output_key="boosted_score",
        )

        node3 = ToolNode(
            node_id="format_node",
            tool=format_tool,
            input_mapping={
                "prefix": "Player ",
                "name": "@state:user.data.name",
                "final_score": "@state:boosted_score",
            },
            output_key="formatted_result",
        )

        flow = Agent(
            agent_id="nested_flow",
            name="Nested State Agent",
            entry="setup_node",
            nodes={
                "setup_node": node1,
                "boost_node": node2,
                "format_node": node3,
            },
            edges=[
                Edge(from_node="setup_node", to_node="boost_node"),
                Edge(from_node="boost_node", to_node="format_node"),
                Edge(from_node="format_node", to_node=None),
            ],
            variables={
                "player_name": "Alice",
                "boost_amount": 50,
            },
        )

        state = make_state(content="start")
        result = await flow.run(state)

        assert result["user"]["data"]["score"] == 100
        assert result["user"]["data"]["name"] == "Alice"
        assert result["boosted_score"] == 150
        assert result["formatted_result"] == "Player Alice: 150"

    @pytest.mark.asyncio
    async def test_tool_modifies_state_for_next_tool(self):
        """
        Тест где каждый tool записывает результат который читает следующий.
        
        Симулирует реальный сценарий обработки данных:
        1. extract: извлекает данные, записывает extracted_data
        2. transform: трансформирует @state:extracted_data, записывает transformed_data
        3. validate: валидирует @state:transformed_data + @var:threshold
        4. save: сохраняет все с @state: и констант
        """
        extract_tool = InlineTool(
            tool_id="extract",
            code="def execute(args, state):\n    return {'items': args['raw'].split(','), 'count': len(args['raw'].split(','))}",
        )

        transform_tool = InlineTool(
            tool_id="transform",
            code="def execute(args, state):\n    return [item.strip().upper() for item in args['data']['items']]",
        )

        validate_tool = InlineTool(
            tool_id="validate",
            code="def execute(args, state):\n    return len(args['items']) >= args['min_count']",
        )

        save_tool = InlineTool(
            tool_id="save",
            code="def execute(args, state):\n    return {'items': args['items'], 'valid': args['is_valid'], 'source': args['source']}",
        )

        node1 = ToolNode(
            node_id="extract_node",
            tool=extract_tool,
            input_mapping={"raw": "@state:raw_input"},
            output_key="extracted_data",
        )

        node2 = ToolNode(
            node_id="transform_node",
            tool=transform_tool,
            input_mapping={"data": "@state:extracted_data"},
            output_key="transformed_data",
        )

        node3 = ToolNode(
            node_id="validate_node",
            tool=validate_tool,
            input_mapping={
                "items": "@state:transformed_data",
                "min_count": "@var:min_items",
            },
            output_key="is_valid",
        )

        node4 = ToolNode(
            node_id="save_node",
            tool=save_tool,
            input_mapping={
                "items": "@state:transformed_data",
                "is_valid": "@state:is_valid",
                "source": "api",  # константа
            },
            output_key="saved_result",
        )

        flow = Agent(
            agent_id="pipeline_flow",
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
        )

        state = make_state(raw_input="apple, banana, cherry")
        result = await flow.run(state)

        # Проверяем весь pipeline
        assert result["extracted_data"]["count"] == 3
        assert result["transformed_data"] == ["APPLE", "BANANA", "CHERRY"]
        assert result["is_valid"] is True
        assert result["saved_result"]["items"] == ["APPLE", "BANANA", "CHERRY"]
        assert result["saved_result"]["valid"] is True
        assert result["saved_result"]["source"] == "api"

    @pytest.mark.asyncio
    async def test_mixed_function_and_tool_nodes_data_flow(self):
        """
        Тест смешанного flow: FunctionNode и ToolNode передают данные друг другу.
        
        1. FunctionNode: устанавливает начальные данные в state
        2. ToolNode: читает @state:, модифицирует
        3. FunctionNode: читает результат tool, добавляет свое
        4. ToolNode: финализирует с @state: и @var:
        """
        multiply_tool = InlineTool(
            tool_id="multiply",
            code="def execute(args, state):\n    return args['x'] * args['y']",
        )

        finalize_tool = InlineTool(
            tool_id="finalize",
            code="def execute(args, state):\n    return f\"Result: {args['value']} (bonus: {args['bonus']})\"",
        )

        def init_func_code(state):
            state.x_value = 7
            state.y_value = 8
            return state
        
        init_func = FunctionNode(
            node_id="init_func",
            code=init_func_code,
        )

        tool_node1 = ToolNode(
            node_id="multiply_node",
            tool=multiply_tool,
            input_mapping={
                "x": "@state:x_value",
                "y": "@state:y_value",
            },
            output_key="product",
        )

        def process_func_code(state):
            state.processed_value = state.product + 100
            return state
        
        process_func = FunctionNode(
            node_id="process_func",
            code=process_func_code,
        )

        tool_node2 = ToolNode(
            node_id="finalize_node",
            tool=finalize_tool,
            input_mapping={
                "value": "@state:processed_value",
                "bonus": "@var:bonus_text",
            },
            output_key="final_message",
        )

        flow = Agent(
            agent_id="mixed_flow",
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
        )

        state = make_state(content="start")
        result = await flow.run(state)

        assert result["x_value"] == 7
        assert result["y_value"] == 8
        assert result["product"] == 56  # 7 * 8
        assert result["processed_value"] == 156  # 56 + 100
        assert result["final_message"] == "Result: 156 (bonus: +VIP)"

