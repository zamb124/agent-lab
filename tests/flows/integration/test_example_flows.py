"""
Интеграционные тесты для example_react и example_graph flows.
Покрывают все возможные варианты использования.
Messages - это A2A типы.
"""

import time
from typing import List

import pytest
import pytest_asyncio
from a2a.types import Message
from a2a.utils.message import get_message_text

from apps.flows.src.models.flow_config import SimpleEdgeCondition


def msg_role(msg) -> str:
    """Извлекает role из A2A Message или dict."""
    if isinstance(msg, dict):
        metadata = msg.get("metadata") or {}
        if metadata.get("tool_call_id"):
            return "tool"
        role = msg.get("role", "user")
        return role.value if hasattr(role, "value") else str(role)

    metadata = msg.metadata if hasattr(msg, "metadata") else None
    if metadata and metadata.get("tool_call_id"):
        return "tool"
    return msg.role.value if hasattr(msg.role, "value") else str(msg.role)


def msg_text(msg) -> str:
    """Извлекает текст из A2A Message или dict."""
    if isinstance(msg, dict):
        if "content" in msg:
            return msg["content"] or ""
        parts = msg.get("parts", [])
        for part in parts:
            if isinstance(part, dict):
                root = part.get("root", part)
                if isinstance(root, dict) and "text" in root:
                    return root["text"]
        return ""
    return get_message_text(msg)


def filter_messages_by_role(messages: List[Message], role: str) -> List[Message]:
    """Фильтрует messages по role."""
    return [m for m in messages if msg_role(m) == role]


from apps.flows.src.container import get_container  # noqa: E402
from apps.flows.src.container_contracts import FlowRuntimeContainer  # noqa: E402
from apps.flows.src.models import FlowConfig  # noqa: E402
from apps.flows.src.runtime.flow import Flow  # noqa: E402
from core.state import ExecutionState  # noqa: E402
from tests.flows.durable_runtime_harness import run_flow, run_node, workflow_state  # noqa: E402


def make_flow_state(
    *,
    flow_id: str,
    content: str,
    branch_id: str = "default",
    unique_id: str | None = None,
    **extra: object,
) -> ExecutionState:
    return workflow_state(
        flow_id=flow_id,
        unique_id=unique_id or str(time.time_ns()),
        branch_id=branch_id,
        content=content,
        **extra,
    )


async def run_loaded_flow(
    *,
    container: FlowRuntimeContainer,
    flow: Flow | None,
    state: ExecutionState,
) -> ExecutionState:
    assert flow is not None
    return await run_flow(container=container, flow=flow, state=state)


class TestExampleReactAgent:
    """Тесты для example_react flow."""

    @pytest_asyncio.fixture
    async def flow_config(self, app) -> FlowConfig:
        """Загружает конфиг example_react из БД."""
        container = get_container()
        config = await container.flow_repository.get("example_react")
        assert config is not None, "Agent example_react не найден в БД"
        return config

    @pytest.mark.asyncio
    async def test_flow_loaded(self, flow_config):
        """Agent загружен в БД."""
        assert flow_config.flow_id == "example_react"
        assert flow_config.name == "Пример ReAct flow"
        assert "example" in flow_config.tags
        assert "react" in flow_config.tags

    @pytest.mark.asyncio
    async def test_flow_has_entry(self, flow_config):
        """Agent имеет точку входа."""
        assert flow_config.entry == "main"
        assert "main" in flow_config.nodes

    @pytest.mark.asyncio
    async def test_flow_has_edges_for_termination(self, flow_config):
        """ReAct flow может иметь edges для терминации нод."""
        assert isinstance(flow_config.edges, list)

    @pytest.mark.asyncio
    async def test_flow_has_variables(self, flow_config):
        """Agent имеет variables с @var: ссылками."""
        from apps.flows.src.models.flow_config import FlowVariableConfig

        assert "company_name" in flow_config.variables
        var = flow_config.variables["company_name"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "@var:company_name"
        assert var.public is True

        assert "max_response_length" in flow_config.variables
        var = flow_config.variables["max_response_length"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "500"
        assert var.public is True

        assert "support_contacts" in flow_config.variables
        var = flow_config.variables["support_contacts"]
        assert isinstance(var, FlowVariableConfig)
        assert var.public is False

    @pytest.mark.asyncio
    async def test_flow_has_skills(self, flow_config):
        """Agent имеет skills."""
        assert "concise" in flow_config.branches
        assert "detailed" in flow_config.branches
        assert "no_subflow" in flow_config.branches
        assert "direct_mode" in flow_config.branches

    @pytest.mark.asyncio
    async def test_skill_concise_overrides_variables(self, flow_config, container):
        """Skill 'concise' переопределяет max_response_length."""
        from apps.flows.src.models.flow_config import FlowVariableConfig

        skill = flow_config.branches["concise"]
        assert skill.name == "Краткие ответы"
        var = skill.variables["max_response_length"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "200"
        assert skill.variables_mode == "merge"

        # Применяем skill
        effective = container.flow_factory.apply_branch(flow_config, "concise")
        assert effective["variables"]["max_response_length"] == "200"
        # Остальные variables сохраняются (merge mode)
        assert effective["variables"]["company_name"] == "@var:company_name"

    @pytest.mark.asyncio
    async def test_skill_detailed_overrides_variables(self, flow_config, container):
        """Skill 'detailed' переопределяет max_response_length."""
        from apps.flows.src.models.flow_config import FlowVariableConfig

        skill = flow_config.branches["detailed"]
        assert skill.name == "Подробные ответы"
        var = skill.variables["max_response_length"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "2000"

        effective = container.flow_factory.apply_branch(flow_config, "detailed")
        assert effective["variables"]["max_response_length"] == "2000"

    @pytest.mark.asyncio
    async def test_skill_variables_replace_mode(self, flow_config, container):
        """Skill 'variables_replace' заменяет все flow variables (variables_mode=replace)."""
        skill = flow_config.branches["variables_replace"]
        assert skill.variables_mode == "replace"
        effective = container.flow_factory.apply_branch(flow_config, "variables_replace")
        assert effective["variables"]["max_response_length"] == "100"
        assert "company_name" not in effective["variables"]

    @pytest.mark.asyncio
    async def test_skill_no_subflow_replaces_nodes(self, flow_config, container):
        """Skill 'no_subflow' заменяет nodes."""
        skill = flow_config.branches["no_subflow"]
        assert skill.name == "Без вложенного subflow"
        assert skill.nodes_mode == "replace"

        effective = container.flow_factory.apply_branch(flow_config, "no_subflow")
        # Должен быть только один node из skill
        assert "main" in effective["nodes"]
        # tools без субагента
        assert "example_subflow" not in effective["nodes"]["main"].get("tools", [])

    @pytest.mark.asyncio
    async def test_skill_direct_mode_changes_entry(self, flow_config, container):
        """Skill 'direct_mode' меняет точку входа."""
        skill = flow_config.branches["direct_mode"]
        assert skill.name == "Прямой вход в subflow"
        assert skill.entry == "direct_subflow"

        effective = container.flow_factory.apply_branch(flow_config, "direct_mode")
        assert effective["entry"] == "direct_subflow"

    @pytest.mark.asyncio
    async def test_flow_factory_applies_entry_skill(self, app):
        """FlowFactory применяет entry из skill."""
        container = get_container()

        flow = await container.flow_factory.get_flow("example_react", branch_id="direct_mode")
        assert flow is not None
        assert flow.entry == "direct_subflow"

    @pytest.mark.asyncio
    async def test_nodes_from_bundle_loaded(self, app):
        """Ноды из nodes.json загружены в БД."""
        container = get_container()

        main_agent = await container.node_repository.get("example_main_agent")
        assert main_agent is not None, "example_main_agent не найден"
        assert main_agent.name == "Main Node"
        assert "calculator" in [t.tool_id for t in main_agent.tools]
        assert "example_subflow" in [t.tool_id for t in main_agent.tools]

        subagent = await container.node_repository.get("example_subflow")
        assert subagent is not None, "example_subflow не найден"
        assert subagent.name == "Subflow-помощник"
        assert "ask_user" in [t.tool_id for t in subagent.tools]

    @pytest.mark.asyncio
    async def test_main_node_inlined(self, flow_config):
        """Нода main собрана с inline кодом из nodes.json."""
        main_node = flow_config.nodes["main"]
        assert main_node["type"] == "llm_node"
        # Нода должна содержать prompt (инлайн), а не ссылку node_id
        assert "prompt" in main_node and main_node["prompt"], "prompt должен быть инлайн"
        # Нода должна содержать tools (инлайн)
        assert "tools" in main_node and len(main_node["tools"]) > 0, "tools должны быть инлайн"
        # Нода должна содержать llm config
        assert "llm" in main_node, "llm config должен быть инлайн"

    @pytest.mark.asyncio
    async def test_direct_subflow_node_inlined(self, flow_config):
        """Нода direct_subflow собрана с inline кодом."""
        node = flow_config.nodes["direct_subflow"]
        assert node["type"] == "llm_node"
        # Нода должна содержать prompt (инлайн)
        assert "prompt" in node and node["prompt"], "prompt должен быть инлайн"
        # Нода должна содержать tools (инлайн)
        assert "tools" in node, "tools должны быть инлайн"

    @pytest.mark.asyncio
    async def test_subagent_tool_inlined_in_main(self, flow_config):
        """Субагент инлайнится как tool в main ноде."""
        main_node = flow_config.nodes["main"]
        tools = main_node.get("tools", [])
        # Ищем tool example_subflow среди инлайн tools
        subagent_tool = None
        for t in tools:
            if isinstance(t, dict) and t.get("tool_id") == "example_subflow":
                subagent_tool = t
                break
        assert subagent_tool is not None, "example_subflow должен быть в tools main ноды"
        # Субагент должен содержать prompt (инлайн)
        assert subagent_tool.get("prompt"), "субагент должен иметь инлайн prompt"

    @pytest.mark.asyncio
    async def test_flow_factory_creates_flow(self, app):
        """FlowFactory создает flow из конфига."""
        container = get_container()

        flow = await container.flow_factory.get_flow("example_react")
        assert flow is not None
        assert flow.entry == "main"

    @pytest.mark.asyncio
    async def test_flow_factory_applies_skill(self, app):
        """FlowFactory применяет skill при создании flow."""
        container = get_container()

        flow = await container.flow_factory.get_flow("example_react", branch_id="concise")
        assert flow is not None
        # Variables из skill должны быть применены
        assert flow.variables.get("max_response_length") == "200"


class TestExampleGraphAgent:
    """Тесты для example_graph flow."""

    @pytest_asyncio.fixture
    async def flow_config(self, app) -> FlowConfig:
        """Загружает конфиг example_graph из БД."""
        container = get_container()
        config = await container.flow_repository.get("example_graph")
        assert config is not None, "Agent example_graph не найден в БД"
        return config

    @pytest.mark.asyncio
    async def test_flow_loaded(self, flow_config):
        """Agent загружен в БД."""
        assert flow_config.flow_id == "example_graph"
        assert flow_config.name == "Пример графового flow"
        assert "example" in flow_config.tags
        assert "graph" in flow_config.tags

    @pytest.mark.asyncio
    async def test_flow_has_entry(self, flow_config):
        """Agent имеет точку входа classifier."""
        assert flow_config.entry == "classifier"
        assert "classifier" in flow_config.nodes

    @pytest.mark.asyncio
    async def test_flow_has_all_nodes(self, flow_config):
        """Agent содержит все ноды."""
        expected_nodes = [
            "classifier",
            "order_processor",
            "complaint_processor",
            "general_processor",
            "formatter",
        ]
        for node in expected_nodes:
            assert node in flow_config.nodes, f"Node {node} не найден"

    @pytest.mark.asyncio
    async def test_classifier_is_inline_code(self, flow_config):
        """Classifier - code нода с inline code."""
        classifier = flow_config.nodes["classifier"]
        assert classifier["type"] == "code"
        assert "code" in classifier
        assert "async def run(args, state):" in classifier["code"]

    @pytest.mark.asyncio
    async def test_formatter_has_inlined_code(self, flow_config):
        """Formatter - code нода с инлайненным кодом."""
        formatter = flow_config.nodes["formatter"]
        assert formatter["type"] == "code"
        assert "code" in formatter
        assert "def format_response" in formatter["code"]

    @pytest.mark.asyncio
    async def test_order_processor_inlined(self, flow_config):
        """Order processor собран с inline кодом."""
        node = flow_config.nodes["order_processor"]
        assert node["type"] == "llm_node"
        assert "prompt" in node and node["prompt"], "prompt должен быть инлайн"

    @pytest.mark.asyncio
    async def test_complaint_processor_inlined(self, flow_config):
        """Complaint processor собран с inline кодом."""
        node = flow_config.nodes["complaint_processor"]
        assert node["type"] == "llm_node"
        # Нода должна содержать prompt (инлайн)
        assert "prompt" in node and node["prompt"], "prompt должен быть инлайн"

    @pytest.mark.asyncio
    async def test_general_processor_is_inline(self, flow_config):
        """General processor - inline конфиг."""
        node = flow_config.nodes["general_processor"]
        assert node["type"] == "llm_node"
        assert "prompt" in node
        assert "flow_id" not in node

    @pytest.mark.asyncio
    async def test_flow_has_conditional_edges(self, flow_config):
        """Agent имеет условные переходы."""
        edges_from_classifier = [e for e in flow_config.edges if e.from_node == "classifier"]
        assert len(edges_from_classifier) == 8

        conditions = {
            (condition.variable, condition.operator, condition.value)
            for condition in (e.condition for e in edges_from_classifier)
            if isinstance(condition, SimpleEdgeCondition)
        }
        assert ("route", "==", "order") in conditions
        assert ("route", "==", "complaint") in conditions
        assert ("route", "==", "general") in conditions
        assert ("route", "==", "cat") in conditions
        assert ("route", "==", "greeting") in conditions
        assert ("route", "==", "operator") in conditions
        assert ("route", "==", "takeover") in conditions

        # Проверяем что есть два edge с условием route == 'general'
        general_edges = [
            e
            for e in edges_from_classifier
            if isinstance(e.condition, SimpleEdgeCondition)
            and e.condition.variable == "route"
            and e.condition.operator == "=="
            and e.condition.value == "general"
        ]
        assert len(general_edges) == 2

        to_nodes = [e.to_node for e in general_edges]
        assert "general_processor" in to_nodes
        assert "prepare_user_data" in to_nodes

    @pytest.mark.asyncio
    async def test_flow_has_variables(self, flow_config):
        """Agent имеет variables."""
        from apps.flows.src.models.flow_config import FlowVariableConfig

        assert "company_name" in flow_config.variables
        assert "order_prefix" in flow_config.variables
        var = flow_config.variables["order_prefix"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "ORD-"
        assert "complaint_prefix" in flow_config.variables
        var = flow_config.variables["complaint_prefix"]
        assert isinstance(var, FlowVariableConfig)
        assert var.value == "CMP-"

    @pytest.mark.asyncio
    async def test_flow_has_skills(self, flow_config):
        """Agent имеет skills."""
        assert "fast_track" in flow_config.branches
        assert "orders_only" in flow_config.branches

    @pytest.mark.asyncio
    async def test_skill_fast_track_replaces_edges(self, flow_config, container):
        """Skill 'fast_track' заменяет edges: LLM-процессоры → null, hitl-ноды → formatter."""
        skill = flow_config.branches["fast_track"]
        assert skill.name == "Быстрая обработка"
        assert skill.edges_mode == "replace"

        effective = container.flow_factory.apply_branch(flow_config, "fast_track")

        # LLM-процессоры ведут в null (пропуск formatter)
        for processor in ["order_processor", "complaint_processor", "general_processor"]:
            processor_edges = [e for e in effective["edges"] if e.from_node == processor]
            if processor_edges:
                assert processor_edges[0].to_node is None

        # hitl, cat, greeting ведут в formatter (см. fast_track edges)
        edges_to_formatter = [e for e in effective["edges"] if e.to_node == "formatter"]
        hitl_sources = {e.from_node for e in edges_to_formatter}
        assert hitl_sources >= {
            "hitl_queue_demo",
            "hitl_takeover_demo",
            "cat_fact_api",
            "greeting_node",
        }

    @pytest.mark.asyncio
    async def test_skill_orders_only_merges_nodes(self, flow_config, container):
        """Skill 'orders_only' мержит nodes с новым classifier."""
        skill = flow_config.branches["orders_only"]
        assert skill.name == "Только заказы"
        assert skill.nodes_mode == "merge"

        effective = container.flow_factory.apply_branch(flow_config, "orders_only")

        # Classifier заменен на упрощенный
        classifier_code = effective["nodes"]["classifier"]["code"]
        assert "complaint" not in classifier_code.lower() or "жалоба" not in classifier_code.lower()

        # Edges только для order и general
        edges_from_classifier = [e for e in effective["edges"] if e.from_node == "classifier"]
        conditions = {
            (condition.variable, condition.operator, condition.value)
            for condition in (e.condition for e in edges_from_classifier)
            if isinstance(condition, SimpleEdgeCondition)
        }
        assert ("route", "==", "order") in conditions
        assert ("route", "==", "general") in conditions
        assert ("route", "==", "complaint") not in conditions

    @pytest.mark.asyncio
    async def test_example_graph_nodes_loaded(self, app):
        """Ноды example_graph из nodes.json загружены в БД."""
        container = get_container()

        order_agent = await container.node_repository.get("example_order_agent")
        assert order_agent is not None, "example_order_agent не найден"
        assert order_agent.name == "Агент заказов"

        complaint_agent = await container.node_repository.get("example_complaint_agent")
        assert complaint_agent is not None, "example_complaint_agent не найден"
        assert complaint_agent.name == "Агент жалоб"

    @pytest.mark.asyncio
    async def test_flow_factory_creates_flow(self, app):
        """FlowFactory создает flow из конфига."""
        container = get_container()

        flow = await container.flow_factory.get_flow("example_graph")
        assert flow is not None
        assert flow.entry == "classifier"

    @pytest.mark.asyncio
    async def test_classifier_routes_to_order(self, flow_config, container, unique_id):
        """Classifier роутит на order при соответствующем content."""
        from apps.flows.src.runtime.nodes import create_node

        classifier_config = flow_config.nodes["classifier"]
        classifier_node = await create_node(
            "classifier",
            classifier_config,
            container=container,
        )

        state = workflow_state(
            flow_id=flow_config.flow_id,
            unique_id=unique_id,
            content="Хочу узнать про мой заказ",
        )
        result = await run_node(container=container, node=classifier_node, state=state)

        assert result["route"] == "order"

    @pytest.mark.asyncio
    async def test_classifier_routes_to_complaint(self, flow_config, container, unique_id):
        """Classifier роутит на complaint при соответствующем content."""
        from apps.flows.src.runtime.nodes import create_node

        classifier_config = flow_config.nodes["classifier"]
        classifier_node = await create_node(
            "classifier",
            classifier_config,
            container=container,
        )

        state = workflow_state(
            flow_id=flow_config.flow_id,
            unique_id=unique_id,
            content="У меня жалоба на сервис",
        )
        result = await run_node(container=container, node=classifier_node, state=state)

        assert result["route"] == "complaint"

    @pytest.mark.asyncio
    async def test_classifier_routes_to_general(self, flow_config, container, unique_id):
        """Classifier роутит на general для обычных вопросов."""
        from apps.flows.src.runtime.nodes import create_node

        classifier_config = flow_config.nodes["classifier"]
        classifier_node = await create_node(
            "classifier",
            classifier_config,
            container=container,
        )

        state = workflow_state(
            flow_id=flow_config.flow_id,
            unique_id=unique_id,
            content="Какой у вас график работы?",
        )
        result = await run_node(container=container, node=classifier_node, state=state)

        assert result["route"] == "general"

    @pytest.mark.asyncio
    async def test_formatter_function(self, app):
        """Formatter функция работает."""
        from apps.flows.bundles.example_graph.nodes import format_response

        state = make_flow_state(
            flow_id="example_graph",
            content="",
            route="order",
            response="Ваш заказ готов",
        )
        result = format_response(state.model_dump())

        assert result["response"] == "[ORDER] Ваш заказ готов"
        assert result["processed"] is True


class TestExampleFlowsIntegration:
    """Интеграционные тесты обоих flows вместе."""

    @pytest.mark.asyncio
    async def test_both_flows_loaded(self, app):
        """Оба flow загружены в БД."""
        container = get_container()

        react_flow = await container.flow_repository.get("example_react")
        graph_flow = await container.flow_repository.get("example_graph")

        assert react_flow is not None
        assert graph_flow is not None

    @pytest.mark.asyncio
    async def test_all_agents_loaded(self, app):
        """Все ноды из обоих agents загружены."""
        container = get_container()

        expected_nodes = [
            "example_main_agent",
            "example_subflow",
            "example_order_agent",
            "example_complaint_agent",
        ]

        for node_id in expected_nodes:
            node = await container.node_repository.get(node_id)
            assert node is not None, f"Node {node_id} не найдена"

    @pytest.mark.asyncio
    async def test_tools_in_repository(self, app):
        """Базовые tools загружены в БД с code."""
        container = get_container()

        calculator = await container.tool_repository.get("calculator")
        ask_user = await container.tool_repository.get("ask_user")

        assert calculator is not None, "calculator tool не найден в БД"
        assert calculator.code is not None, "calculator должен иметь inline code"

        assert ask_user is not None, "ask_user tool не найден в БД"
        assert ask_user.code is not None, "ask_user должен иметь inline code"

    @pytest.mark.asyncio
    async def test_branch_id_preserved_in_state(self, app):
        """branch_id сохраняется в state при выполнении."""
        container = get_container()

        flow = await container.flow_factory.get_flow("example_react", branch_id="concise")

        # Проверяем что ветка применена через variables
        assert flow.variables.get("max_response_length") == "200"


class TestExampleReactE2E:
    """E2E тесты example_react с MockLLM."""

    @pytest.mark.asyncio
    async def test_basic_flow_execution(self, app, mock_llm_with_queue):
        """Базовое выполнение flow - агент отвечает напрямую."""
        mock_llm_with_queue(["Привет! Я ваш ассистент. Чем могу помочь?"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="Привет")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result
        assert result.current_nodes == []  # Agent завершен

    @pytest.mark.asyncio
    @pytest.mark.xdist_group(name="calculator")
    async def test_flow_with_calculator_tool(self, app, mock_llm_with_queue, unique_id):
        """Агент использует calculator tool."""
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "25 * 4"}},
                "Результат вычисления: 100",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(
            flow_id="example_react",
            unique_id=f"calc-{unique_id}",
            content="Сколько будет 25 умножить на 4?",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result
        assert "tool_results" in result.model_dump()
        assert "calculator" in result.model_dump()["tool_results"]

    @pytest.mark.asyncio
    async def test_flow_with_interrupt(self, app, mock_llm_with_queue, sync_tools):
        """Агент запрашивает информацию у пользователя через ask_user."""
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="Хочу познакомиться")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Interrupt возвращается в state
        assert result.interrupt is not None
        assert result.interrupt.question == "Как вас зовут?"

    @pytest.mark.asyncio
    async def test_flow_with_subagent_tool(self, app, mock_llm_with_queue, sync_tools):
        """Агент делегирует задачу субагенту."""
        mock_llm_with_queue(
            [
                # Главный агент вызывает субагента
                {
                    "type": "tool_call",
                    "tool": "example_subflow",
                    "args": {"query": "Узнай у пользователя город"},
                },
                # Субагент спрашивает
                {
                    "type": "tool_call",
                    "tool": "ask_user",
                    "args": {"question": "В каком городе вы находитесь?"},
                },
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="Нужна информация о локации")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Interrupt возвращается в state
        assert result.interrupt is not None
        assert "город" in result.interrupt.question.lower()

    @pytest.mark.asyncio
    async def test_skill_concise_execution(self, app, mock_llm_with_queue):
        """Выполнение с skill 'concise' - переменные применены."""
        mock_llm_with_queue(["Краткий ответ."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react", branch_id="concise")

        # Проверяем переменные
        assert flow.variables.get("max_response_length") == "200"

        state = make_flow_state(
            flow_id="example_react",
            branch_id="concise",
            content="Что-нибудь",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result
        # Variables доступны в state
        assert result.variables["max_response_length"] == "200"

    @pytest.mark.asyncio
    async def test_skill_detailed_execution(self, app, mock_llm_with_queue):
        """Выполнение с skill 'detailed' - переменные применены."""
        mock_llm_with_queue(["Подробный развернутый ответ с деталями."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react", branch_id="detailed")

        assert flow.variables.get("max_response_length") == "2000"

        state = make_flow_state(
            flow_id="example_react",
            branch_id="detailed",
            content="Расскажи подробно",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.variables["max_response_length"] == "2000"

    @pytest.mark.asyncio
    async def test_skill_direct_mode_entry(self, app, mock_llm_with_queue):
        """Skill 'direct_mode' меняет точку входа на субагента."""
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "ask_user",
                    "args": {"question": "Что вы хотите узнать?"},
                },
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react", branch_id="direct_mode")

        # Entry изменен на direct_subflow
        assert flow.entry == "direct_subflow"

        state = make_flow_state(
            flow_id="example_react",
            branch_id="direct_mode",
            content="Начать",
        )

        # Субагент сразу задает вопрос через interrupt (сохраняется в state)
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.interrupt is not None
        assert "узнать" in result.interrupt.question.lower()

    @pytest.mark.asyncio
    async def test_skill_no_subflow_no_delegation(self, app, mock_llm_with_queue):
        """Skill 'no_subflow' — главная нода отвечает без делегирования в subflow."""
        mock_llm_with_queue(["Отвечаю сам без делегирования."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react", branch_id="no_subflow")

        state = make_flow_state(
            flow_id="example_react",
            branch_id="no_subflow",
            content="Вопрос",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result
        # Субагент не использовался
        assert "example_subflow" not in result.tool_results


class TestExampleGraphE2E:
    """E2E тесты example_graph с MockLLM."""

    @pytest.mark.asyncio
    async def test_route_to_order_processor(self, app, mock_llm_with_queue):
        """Роутинг на order_processor."""
        mock_llm_with_queue(["Ваш заказ ORD-12345678 в пути."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="Где мой заказ?")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Classifier определил route = order
        assert result.get("route") == "order"
        # Formatter добавил префикс
        assert "[ORDER]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_route_to_complaint_processor(self, app, mock_llm_with_queue):
        """Роутинг на complaint_processor."""
        mock_llm_with_queue(
            ["Приносим извинения за неудобства. Ваше обращение CMP-12345678 зарегистрировано."]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="Хочу подать жалобу на сервис")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "complaint"
        assert "[COMPLAINT]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_route_to_general_processor(self, app, mock_llm_with_queue):
        """Роутинг на general_processor."""
        mock_llm_with_queue(["Мы работаем с 9:00 до 18:00."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="Какой у вас график работы?")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "general"
        assert "[GENERAL]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_order_processor_with_interrupt(self, app, mock_llm_with_queue):
        """Order processor запрашивает номер заказа."""
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "ask_user",
                    "args": {"question": "Назовите номер вашего заказа"},
                },
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="Проверить статус заказа")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.interrupt is not None
        assert "заказ" in result.interrupt.question.lower()

    @pytest.mark.asyncio
    async def test_skill_fast_track_skips_formatter(self, app, mock_llm_with_queue):
        """Skill 'fast_track' пропускает formatter."""
        mock_llm_with_queue(["Быстрый ответ без форматирования."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

        state = make_flow_state(
            flow_id="example_graph",
            branch_id="fast_track",
            content="Срочный вопрос про заказ",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "order"
        # Formatter пропущен - нет префикса и processed
        assert "[ORDER]" not in result.get("response", "")
        assert result.get("processed") is None

    @pytest.mark.asyncio
    async def test_skill_orders_only_no_complaint_route(self, app, mock_llm_with_queue):
        """Skill 'orders_only' направляет жалобы в general."""
        mock_llm_with_queue(["Для жалоб обратитесь по телефону."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

        # Жалоба идет в general (так как complaint route убран)
        state = make_flow_state(
            flow_id="example_graph",
            branch_id="orders_only",
            content="Хочу подать жалобу",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # С этим skill жалобы идут в general
        assert result.get("route") == "general"

    @pytest.mark.asyncio
    async def test_variables_in_agent_prompts(self, app, mock_llm_with_queue):
        """Variables доступны в промптах агентов."""
        mock_llm_with_queue(["Ваш заказ ORD-12345678 обрабатывается."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="Статус order")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Variables переданы в state
        assert result.variables.get("order_prefix") == "ORD-"
        assert result.variables.get("complaint_prefix") == "CMP-"

    @pytest.mark.asyncio
    async def test_complaint_processor_with_interrupt(self, app, mock_llm_with_queue):
        """Complaint processor запрашивает детали жалобы."""
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "ask_user",
                    "args": {"question": "Опишите вашу проблему подробнее"},
                },
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(flow_id="example_graph", content="У меня серьезная жалоба")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.interrupt is not None
        assert "проблем" in result.interrupt.question.lower()

    @pytest.mark.asyncio
    async def test_variables_from_metadata_override_flow_variables(self, app, mock_llm_with_queue):
        """Variables из metadata переопределяют flow variables."""
        mock_llm_with_queue(["Ответ с переопределенными переменными."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        # Agent имеет переменную company_name
        assert "company_name" in flow.variables

        # Обновляем variables flow (симулируем переопределение из metadata)
        # В реальности это делается в BaseChannel.process_task()
        flow.variables["company_name"] = "MetadataCompany"
        flow.variables["max_response_length"] = "300"

        state = make_flow_state(flow_id="example_react", content="Тест")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert result.variables["company_name"] == "MetadataCompany"
        assert result.variables["max_response_length"] == "300"

    @pytest.mark.asyncio
    async def test_dict_variables_from_metadata(self, app, mock_llm_with_queue):
        """Dict переменные из metadata доступны в промптах через точку."""
        mock_llm_with_queue(["Ответ с dict переменными."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        # Обновляем variables с dict объектом (симулируем из metadata)
        flow.variables["user_config"] = {
            "name": "TestUser",
            "email": "test@example.com",
            "settings": {
                "theme": "dark",
                "language": "ru",
            },
        }

        state = make_flow_state(flow_id="example_react", content="Тест")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert isinstance(result.variables["user_config"], dict)
        assert result.variables["user_config"]["name"] == "TestUser"
        assert result.variables["user_config"]["settings"]["theme"] == "dark"


class TestExampleFlowsEdgeCases:
    """Граничные случаи и ошибки."""

    @pytest.mark.asyncio
    async def test_empty_content(self, app, mock_llm_with_queue):
        """Пустой content обрабатывается."""
        mock_llm_with_queue(["Пожалуйста, уточните ваш вопрос."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result

    @pytest.mark.asyncio
    async def test_unknown_skill_uses_default(self, app, mock_llm_with_queue):
        """Неизвестный skill использует базовую конфигурацию."""
        mock_llm_with_queue(["Стандартный ответ."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react", branch_id="unknown_skill")

        # Используется базовый entry
        assert flow.entry == "main"

        state = make_flow_state(flow_id="example_react", content="Тест")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result

    @pytest.mark.asyncio
    async def test_multiple_tool_calls(self, app, mock_llm_with_queue, unique_id):
        """Несколько вызовов tools подряд."""
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "10 + 5"}},
                {"type": "tool_call", "tool": "calculator", "args": {"expression": "15 * 2"}},
                "10 + 5 = 15, затем 15 * 2 = 30",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(
            flow_id="example_react",
            unique_id=f"multi-tool-{unique_id}",
            content="Посчитай 10+5, потом умножь на 2",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        assert "response" in result
        assert "calculator" in result.tool_results

    @pytest.mark.asyncio
    async def test_graph_preserves_state_through_nodes(self, app, mock_llm_with_queue):
        """State сохраняется при переходе между нодами графа."""
        mock_llm_with_queue(["Заказ обработан."])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_flow_state(
            flow_id="example_graph",
            content="Мой заказ",
            custom_field="preserved_value",
        )
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Custom field сохранен
        assert result.get("custom_field") == "preserved_value"
        # route добавлен classifier
        assert "route" in result
        # processed добавлен formatter
        assert result.get("processed") is True


class TestSubagentInterruptResume:
    """
    Точные тесты для проверки поведения субагента с interrupt и resume.

    Фиксируем критическое поведение:
    1. При interrupt субагента - сохраняется pending_tool_call
    2. При resume - ответ пользователя идёт НАПРЯМУЮ в субагента
    3. Субагент видит свою историю с ответом пользователя
    4. Главный агент получает только финальный результат

    ВАЖНО: Agent ловит FlowInterrupt и возвращает state с interrupt,
    не бросает исключение наружу. Поэтому тесты проверяют state.interrupt.
    """

    @pytest.mark.asyncio
    async def test_subagent_interrupt_saves_pending_tool_call(
        self, app, mock_llm_with_queue, sync_tools
    ):
        """
        При interrupt от субагента сохраняется interrupt_path.

        Сценарий:
        1. Главный агент вызывает субагента
        2. Субагент вызывает ask_user
        3. В state должен сохраниться __pending_tool_call__ с tool_name субагента
        """
        mock_llm_with_queue(
            [
                # Главный агент вызывает субагента
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "найти цветы"}},
                # Субагент вызывает ask_user
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="где купить цветы")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Agent возвращает state с interrupt
        assert result.interrupt is not None
        assert "город" in result.interrupt.question.lower()

        # КРИТИЧНО: interrupt_path содержит путь к прерыванию
        assert len(result.interrupt_path) > 0

        # КРИТИЧНО: история субагента сохранена в nested_states
        assert "example_subflow" in result.nested_states

    @pytest.mark.asyncio
    async def test_subagent_resume_receives_user_answer_directly(
        self, app, mock_llm_with_queue, sync_tools
    ):
        """
        При resume ответ пользователя идёт НАПРЯМУЮ в субагента, минуя главного.

        Сценарий:
        1. Первый запрос: субагент прерывается
        2. Resume: ответ "москва" должен попасть в историю субагента
        3. Субагент видит: свой запрос + [INTERRUPT] + "москва"
        4. Субагент отвечает
        5. Главный агент получает результат
        """
        mock_llm_with_queue(
            [
                # === ПЕРВЫЙ ЗАПРОС ===
                # Главный агент вызывает субагента
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "найти цветы"}},
                # Субагент вызывает ask_user
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                # === RESUME ===
                # Субагент получает ответ и отвечает
                "В Москве много цветочных магазинов: Флора на Тверской.",
                # Главный агент формирует финальный ответ
                "Магазин Флора на Тверской - отличный выбор!",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        # === ПЕРВЫЙ ЗАПРОС ===
        state = make_flow_state(flow_id="example_react", content="где купить цветы")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Проверяем состояние после interrupt
        assert result.interrupt is not None
        assert len(result.interrupt_path) > 0

        # === RESUME ===
        result.content = "москва"
        final_result = await run_loaded_flow(container=container, flow=flow, state=result)

        # Проверяем что flow завершился с ответом
        assert final_result.get("response") is not None, "Должен быть финальный ответ"

        # КРИТИЧНО: история субагента содержит ответ пользователя как tool response
        nested_states = final_result.nested_states
        subagent_state = nested_states.get("example_subflow")
        if subagent_state:
            subagent_history = (
                subagent_state.messages if hasattr(subagent_state, "messages") else []
            )
        else:
            subagent_history = []

        # Проверяем что ответ пользователя добавлен как tool response в историю субагента
        tool_messages = filter_messages_by_role(subagent_history, "tool")
        tool_contents = [msg_text(m).lower() for m in tool_messages]
        assert any("москва" in content for content in tool_contents), (
            f"Ответ пользователя 'москва' должен быть как tool response в истории субагента: {tool_contents}"
        )

    @pytest.mark.asyncio
    async def test_subagent_multiple_interrupts_preserve_history(
        self, app, mock_llm_with_queue, sync_tools
    ):
        """
        При нескольких interrupt подряд история субагента накапливается.

        Сценарий:
        1. Субагент спрашивает "город?" -> пользователь "москва"
        2. Субагент спрашивает "район?" -> пользователь "раменки"
        3. Субагент отвечает с полной информацией
        """
        mock_llm_with_queue(
            [
                # === ПЕРВЫЙ ЗАПРОС ===
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "найти цветы"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                # === RESUME 1: "москва" ===
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Какой район?"}},
                # === RESUME 2: "раменки" ===
                "Цветочный магазин Флора в Раменках, Москва.",
                # Главный агент
                "Рекомендую Флору в Раменках!",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        # === ПЕРВЫЙ ЗАПРОС ===
        state = make_flow_state(flow_id="example_react", content="где купить цветы")
        result1 = await run_loaded_flow(container=container, flow=flow, state=state)
        assert result1.interrupt is not None
        assert "город" in result1.interrupt.question.lower()

        # === RESUME 1 ===
        result1.content = "москва"
        result2 = await run_loaded_flow(container=container, flow=flow, state=result1)
        assert result2.interrupt is not None
        assert "район" in result2.interrupt.question.lower()

        # Проверяем что история накапливается через nested_states как tool responses
        nested_states = result2.nested_states
        subagent_state = nested_states.get("example_subflow")
        if subagent_state:
            history = subagent_state.messages if hasattr(subagent_state, "messages") else []
        else:
            history = []
        tool_msgs = [msg_text(m).lower() for m in filter_messages_by_role(history, "tool")]
        assert any("москва" in msg for msg in tool_msgs), (
            f"'москва' должна быть как tool response в истории: {tool_msgs}"
        )

        # === RESUME 2 ===
        result2.content = "раменки"
        result3 = await run_loaded_flow(container=container, flow=flow, state=result2)

        # Финальная проверка истории через nested_states
        nested_states3 = result3.nested_states
        subagent_state3 = nested_states3.get("example_subflow")
        if subagent_state3:
            final_history = subagent_state3.messages if hasattr(subagent_state3, "messages") else []
        else:
            final_history = []
        final_tool_msgs = [
            msg_text(m).lower() for m in filter_messages_by_role(final_history, "tool")
        ]

        assert any("москва" in msg for msg in final_tool_msgs), (
            f"'москва' должна сохраниться как tool response в истории: {final_tool_msgs}"
        )
        assert any("раменки" in msg for msg in final_tool_msgs), (
            f"'раменки' должна быть как tool response в истории: {final_tool_msgs}"
        )

        assert "response" in result3

    @pytest.mark.asyncio
    async def test_main_agent_does_not_see_user_answer_on_resume(self, app, mock_llm_with_queue):
        """
        При resume главный агент НЕ видит ответ пользователя напрямую.
        Ответ идёт в субагента, главный видит только результат субагента.

        Это критично: если главный агент увидит "раменки", он может
        сам решить ответить вместо вызова субагента.
        """
        mock_llm_with_queue(
            [
                # === ПЕРВЫЙ ЗАПРОС ===
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "найти цветы"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                # === RESUME ===
                # Субагент отвечает (НЕ главный агент!)
                "Магазин Флора в Москве.",
                # Главный агент формирует финальный ответ
                "Рекомендую Флору!",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        state = make_flow_state(flow_id="example_react", content="где купить цветы")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # Resume
        result.content = "москва"
        final_result = await run_loaded_flow(container=container, flow=flow, state=result)

        # Проверяем что messages главного агента НЕ содержат "москва" как user message
        # (ответ должен идти в субагента, не в главного)
        main_messages = final_result.messages

        # Ищем user message с "москва" в главном агенте
        for msg in main_messages:
            if msg_role(msg) == "user" and "москва" in msg_text(msg).lower():
                # Это нарушение - ответ пользователя попал напрямую в главного агента
                pytest.fail(
                    f"Ответ пользователя 'москва' попал в messages главного агента: {msg}\n"
                    f"Это значит что resume работает неправильно - ответ должен идти в субагента."
                )

        # Финальный ответ должен быть
        assert "response" in final_result

    @pytest.mark.asyncio
    async def test_interrupt_path_mechanism(self, app, mock_llm_with_queue, sync_tools):
        """
        КРИТИЧЕСКИЙ ТЕСТ: механизм InterruptManager с interrupt_path.

        Использует sync_tools чтобы MockLLM работал в том же процессе.

        Проверяет что при interrupt от субагента:
        1. Сохраняется interrupt_path с путём к прерванному вызову
        2. При resume ответ добавляется в историю СУБАГЕНТА через __nested_states__
        3. Субагент вызывается НАПРЯМУЮ (без повторного вызова LLM главного агента)
        4. Финальный результат субагента попадает в историю главного агента
        5. НЕТ [INTERRUPT] костылей в messages
        """
        mock_llm_with_queue(
            [
                # === ПЕРВЫЙ ЗАПРОС: главный агент вызывает субагента ===
                {
                    "type": "tool_call",
                    "tool": "example_subflow",
                    "args": {"query": "найти магазин"},
                },
                # === СУБАГЕНТ: спрашивает город ===
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                # === RESUME: субагент получает ответ и отвечает ===
                "Магазин 'Цветы' на ул. Тверская, Москва.",
                # === ГЛАВНЫЙ АГЕНТ: формирует финальный ответ ===
                "Рекомендую магазин 'Цветы' на Тверской!",
            ]
        )

        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")

        # === ПЕРВЫЙ ЗАПРОС ===
        state = make_flow_state(flow_id="example_react", content="найти цветочный магазин")
        result = await run_loaded_flow(container=container, flow=flow, state=state)

        # ПРОВЕРКА 1: interrupt_path сохранён
        assert len(result.interrupt_path) > 0, (
            f"interrupt_path не должен быть пустым: {result.interrupt_path}"
        )

        # ПРОВЕРКА 2: interrupt содержит вопрос субагента
        assert result.interrupt is not None
        assert "город" in result.interrupt.question.lower(), (
            f"Вопрос должен быть про город: {result.interrupt.question}"
        )

        # ПРОВЕРКА 3: nested_states сохранены (история субагента)
        assert "example_subflow" in result.nested_states, (
            f"Должен быть nested state для example_subflow: {result.nested_states.keys()}"
        )

        # === RESUME С ОТВЕТОМ "москва" ===
        result.content = "москва"
        final_result = await run_loaded_flow(container=container, flow=flow, state=result)

        # ПРОВЕРКА 4: interrupt_path очищен
        assert len(final_result.interrupt_path) == 0, (
            "После resume interrupt_path должен быть очищен"
        )

        # ПРОВЕРКА 5: Ответ пользователя добавлен в историю СУБАГЕНТА как tool response
        nested_states_after = final_result.nested_states
        subagent_state = nested_states_after.get("example_subflow")
        if subagent_state:
            subagent_messages = (
                subagent_state.messages if hasattr(subagent_state, "messages") else []
            )
        else:
            subagent_messages = []
        tool_messages = [msg_text(m) for m in filter_messages_by_role(subagent_messages, "tool")]
        assert any("москва" in content.lower() for content in tool_messages), (
            f"Ответ 'москва' должен быть как tool response в истории субагента: {tool_messages}"
        )

        # ПРОВЕРКА 6: В messages главного агента НЕТ "москва" как user message
        main_messages = final_result.messages
        main_user_messages = [msg_text(m) for m in filter_messages_by_role(main_messages, "user")]
        for content in main_user_messages:
            if "москва" in content.lower():
                pytest.fail(
                    f"КРИТИЧЕСКАЯ ОШИБКА: ответ 'москва' попал в messages главного агента!\n"
                    f"Main user messages: {main_user_messages}"
                )

        # ПРОВЕРКА 7: В messages главного агента есть финальный tool response
        main_tool_messages = filter_messages_by_role(main_messages, "tool")
        tool_contents = [msg_text(m) for m in main_tool_messages]
        assert any("Цветы" in content or "Тверская" in content for content in tool_contents), (
            f"Финальный ответ субагента должен быть в tool messages: {tool_contents}"
        )

        # ПРОВЕРКА 8: НЕТ [INTERRUPT] костылей
        for msg in main_messages:
            content = msg_text(msg)
            assert "[INTERRUPT]" not in content, f"Не должно быть [INTERRUPT] в messages: {msg}"

        # ПРОВЕРКА 9: Финальный ответ
        assert "response" in final_result
        assert "Тверская" in final_result["response"] or "Цветы" in final_result["response"], (
            f"Финальный ответ должен содержать данные от субагента: {final_result['response']}"
        )
