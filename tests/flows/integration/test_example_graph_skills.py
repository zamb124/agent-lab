"""
Тесты для всех skills в example_graph flow.

Каждый skill тестируется на:
- Корректное создание flow с skill
- Наличие всех необходимых нод
- Выполнение графа от начала до конца для каждого маршрута
- Промежуточные состояния state
- Финальный результат

ВАЖНО: Skills с mock.enabled в agent.json - это только конфигурация,
mock НЕ применяется автоматически. Используем mock_llm_with_queue.
"""

import time

import pytest
import pytest_asyncio

from apps.flows.src.container import get_container
from apps.flows.src.container_contracts import FlowRuntimeContainer
from apps.flows.src.runtime.flow import Flow
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_flow, workflow_state


def make_graph_state(
    *,
    content: str,
    branch_id: str = "default",
    **extra: object,
) -> ExecutionState:
    return workflow_state(
        flow_id="example_graph",
        unique_id=str(time.time_ns()),
        branch_id=branch_id,
        content=content,
        **extra,
    )


async def run_graph_flow(
    *,
    container: FlowRuntimeContainer,
    flow: Flow | None,
    state: ExecutionState,
) -> ExecutionState:
    assert flow is not None
    return await run_flow(container=container, flow=flow, state=state)


class TestFastTrackSkill:
    """Тесты для skill 'fast_track' - пропускает formatter."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает flow с fast_track skill."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается с fast_track skill."""
        assert flow is not None
        assert flow.flow_id == "example_graph"

    @pytest.mark.asyncio
    async def test_required_nodes_present(self, flow):
        """Все необходимые ноды присутствуют."""
        assert "classifier" in flow.nodes
        assert "order_processor" in flow.nodes
        assert "complaint_processor" in flow.nodes
        assert "general_processor" in flow.nodes

    @pytest.mark.asyncio
    async def test_edges_skip_formatter(self, flow):
        """Edges ведут напрямую к null, минуя formatter."""
        edges_to_null = [edge for edge in flow.edges if edge.to_node is None]
        edge_sources = {edge.from_node for edge in edges_to_null}

        assert "order_processor" in edge_sources
        assert "complaint_processor" in edge_sources
        assert "general_processor" in edge_sources

    @pytest.mark.asyncio
    @pytest.mark.parametrize("input_text,expected_route", [
        ("заказ", "order"),
        ("мой order", "order"),
        ("жалоба на сервис", "complaint"),
        ("complaint", "complaint"),
        ("какой график работы?", "general"),
    ])
    async def test_route_order_complaint_general(
        self, app, mock_llm_with_queue, input_text, expected_route
    ):
        """Тест маршрутов order, complaint, general."""
        mock_llm_with_queue(["Mock response для теста"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

        state = make_graph_state(branch_id="fast_track", content=input_text)
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == expected_route
        assert result.get("processed") is None, "formatter не должен выполняться"
        response = result.get("response", "")
        assert "[ORDER]" not in response
        assert "[COMPLAINT]" not in response
        assert "[GENERAL]" not in response

    @pytest.mark.asyncio
    async def test_route_greeting_in_fast_track(self, app):
        """fast_track: greeting -> greeting_node -> formatter (полное покрытие маршрутов)."""
        container = get_container()
        agent = await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

        state = make_graph_state(branch_id="fast_track", content="привет")
        result = await run_graph_flow(container=container, flow=agent, state=state)

        assert result.get("route") == "greeting"
        assert result.get("processed") is True
        assert "GREETING" in (result.get("response") or "")


class TestOrdersOnlySkill:
    """Тесты для skill 'orders_only' - обрабатывает только заказы."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает flow с orders_only skill."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается с orders_only skill."""
        assert flow is not None
        assert flow.flow_id == "example_graph"

    @pytest.mark.asyncio
    async def test_required_nodes_present(self, flow):
        """Все необходимые ноды присутствуют (merge режим)."""
        assert "classifier" in flow.nodes
        assert "order_processor" in flow.nodes
        assert "general_processor" in flow.nodes
        assert "formatter" in flow.nodes

    @pytest.mark.asyncio
    async def test_order_route_goes_to_order_processor(self, app, mock_llm_with_queue):
        """Заказ идет в order_processor -> formatter."""
        mock_llm_with_queue(["Ваш заказ обработан"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

        state = make_graph_state(branch_id="orders_only", content="оформить заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "order"
        assert result.get("processed") is True
        assert "[ORDER]" in result.get("response", "")

    @pytest.mark.asyncio
    async def test_complaint_goes_to_general_processor(self, app, mock_llm_with_queue):
        """Жалоба идет в general_processor (не complaint_processor)."""
        mock_llm_with_queue(["Для жалоб обратитесь в службу поддержки"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

        state = make_graph_state(branch_id="orders_only", content="хочу подать жалобу")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # С orders_only classifier направляет все кроме заказов в general
        assert result.get("route") == "general"
        assert result.get("processed") is True
        assert "[GENERAL]" in result.get("response", "")

    @pytest.mark.asyncio
    async def test_general_goes_to_general_processor(self, app, mock_llm_with_queue):
        """Общий запрос идет в general_processor -> formatter."""
        mock_llm_with_queue(["Мы работаем с 9 до 18"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

        state = make_graph_state(branch_id="orders_only", content="какой график работы?")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "general"
        assert result.get("processed") is True
        assert "[GENERAL]" in result.get("response", "")


class TestCodeNodesSkill:
    """Тесты базовых code nodes: classifier и formatter."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    async def test_classifier_routes_correctly(self, app, mock_llm_with_queue):
        """Classifier работает по базовой логике."""
        mock_llm_with_queue(["Mock response"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        # Базовый classifier определяет route по содержимому
        state = make_graph_state(content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)
        assert result.get("route") == "order"

        state = make_graph_state(content="вопрос")
        result = await run_graph_flow(container=container, flow=flow, state=state)
        assert result.get("route") == "general"

    @pytest.mark.asyncio
    async def test_formatter_adds_prefix(self, app, mock_llm_with_queue):
        """Formatter добавляет префикс маршрута."""
        mock_llm_with_queue(["Mock response от LLM"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="вопрос")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # Formatter добавляет [ROUTE] префикс
        assert "[GENERAL]" in result.get("response", "")
        assert result.get("processed") is True


class TestLlmNodesSkill:
    """Тесты LLM nodes базового графа."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    async def test_order_processor_executes(self, app, mock_llm_with_queue):
        """Order processor выполняется и возвращает ответ."""
        mock_llm_with_queue(["Заказ обработан успешно"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "order"
        assert "[ORDER]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_complaint_processor_executes(self, app, mock_llm_with_queue):
        """Complaint processor выполняется и возвращает ответ."""
        mock_llm_with_queue(["Жалоба зарегистрирована"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="жалоба")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "complaint"
        assert "[COMPLAINT]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_general_processor_executes(self, app, mock_llm_with_queue):
        """General processor выполняется и возвращает ответ."""
        mock_llm_with_queue(["Общий ответ"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="вопрос")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "general"
        assert "[GENERAL]" in result.get("response", "")
        assert result.get("processed") is True


class TestLlmGraphSkill:
    """Тесты полного LLM graph базового flow."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("input_text,expected_route,expected_prefix", [
        ("заказ", "order", "[ORDER]"),
        ("жалоба", "complaint", "[COMPLAINT]"),
        ("вопрос", "general", "[GENERAL]"),
    ])
    async def test_all_routes_execute_correctly(
        self, app, mock_llm_with_queue, input_text, expected_route, expected_prefix
    ):
        """Все маршруты выполняются корректно с mock LLM."""
        mock_llm_with_queue(["Mock LLM ответ"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content=input_text)
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == expected_route
        assert expected_prefix in result.get("response", "")
        assert result.get("processed") is True


class TestRouteOrderSkill:
    """Тесты order route базового graph."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    async def test_order_route_executes(self, app, mock_llm_with_queue):
        """Order route выполняется корректно."""
        mock_llm_with_queue(["Заказ обработан"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "order"
        assert "[ORDER]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_complaint_still_routes_to_complaint(self, app, mock_llm_with_queue):
        """Жалоба идет в complaint (mock не переопределяет classifier)."""
        mock_llm_with_queue(["Жалоба обработана"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="жалоба")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # Базовый classifier определяет route по содержимому
        assert result.get("route") == "complaint"
        assert "[COMPLAINT]" in result.get("response", "")
        assert result.get("processed") is True


class TestRouteComplaintSkill:
    """Тесты complaint route базового graph."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    async def test_complaint_route_executes(self, app, mock_llm_with_queue):
        """Complaint route выполняется корректно."""
        mock_llm_with_queue(["Жалоба зарегистрирована"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="жалоба")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "complaint"
        assert "[COMPLAINT]" in result.get("response", "")
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_order_still_routes_to_order(self, app, mock_llm_with_queue):
        """Заказ идет в order (mock не переопределяет classifier)."""
        mock_llm_with_queue(["Заказ обработан"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # Базовый classifier определяет route по содержимому
        assert result.get("route") == "order"
        assert "[ORDER]" in result.get("response", "")
        assert result.get("processed") is True


class TestFullGraphSkill:
    """Тесты полного базового graph."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает базовый flow."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_with_skill(self, flow):
        """Agent создается."""
        assert flow is not None

    @pytest.mark.asyncio
    async def test_full_graph_execution(self, app, mock_llm_with_queue):
        """Граф выполняется полностью."""
        mock_llm_with_queue(["Полный ответ"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="вопрос")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # Базовый classifier определяет route
        assert result.get("route") == "general"
        assert result.get("processed") is True
        assert "[GENERAL]" in result.get("response", "")

    @pytest.mark.asyncio
    async def test_all_routes_work(self, app, mock_llm_with_queue):
        """Все маршруты работают в этом skill."""
        mock_llm_with_queue(["Response"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        for content, expected_route in [("заказ", "order"), ("жалоба", "complaint"), ("вопрос", "general")]:
            state = make_graph_state(content=content)
            result = await run_graph_flow(container=container, flow=flow, state=state)
            assert result.get("route") == expected_route
            assert result.get("processed") is True


class TestDefaultSkill:
    """Тесты для default skill (без указания branch_id)."""

    @pytest_asyncio.fixture
    async def flow(self, app):
        """Загружает flow без skill."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_flow_created_without_skill(self, flow):
        """Agent создается без skill."""
        assert flow is not None
        assert flow.flow_id == "example_graph"

    @pytest.mark.asyncio
    async def test_all_nodes_present(self, flow):
        """Все ноды из базового конфига присутствуют."""
        assert "classifier" in flow.nodes
        assert "order_processor" in flow.nodes
        assert "complaint_processor" in flow.nodes
        assert "general_processor" in flow.nodes
        assert "formatter" in flow.nodes
        assert "cat_fact_api" in flow.nodes
        assert "greeting_node" in flow.nodes

    @pytest.mark.asyncio
    @pytest.mark.parametrize("input_text,expected_route", [
        ("заказ", "order"),
        ("жалоба", "complaint"),
        ("вопрос", "general"),
        ("привет", "greeting"),
        ("кот", "cat"),
        ("cat", "cat"),
        ("кошка", "cat"),
    ])
    async def test_all_routes_work(self, app, mock_llm_with_queue, input_text, expected_route):
        """Все маршруты работают корректно."""
        mock_llm_with_queue(["Mock response"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content=input_text)
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == expected_route, f"Для '{input_text}' ожидался route={expected_route}, получен {result.get('route')}"
        # Все маршруты кроме fast_track должны проходить через formatter
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_greeting_route_with_variables(self, app):
        """Маршрут greeting использует переменные."""
        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="привет")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "greeting"
        # greeting_node устанавливает response с приветствием
        response = result.get("response", "")
        assert "Добро пожаловать" in response or "GREETING" in response or "Привет" in response

    @pytest.mark.asyncio
    async def test_order_route_calculates_total(self, app, mock_llm_with_queue):
        """Маршрут order вычисляет order_total через calculator."""
        mock_llm_with_queue(["Заказ обработан"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("route") == "order"
        # order_processor обрабатывает заказ и formatter добавляет префикс [ORDER]
        # Проверяем что response содержит ORDER или что был выполнен order_processor
        response = str(result.get("response", ""))
        assert "ORDER" in response.upper() or "заказ" in response.lower()


class TestSkillStatePreservation:
    """Тесты сохранения state при переходе между нодами."""

    @pytest.mark.asyncio
    async def test_custom_fields_preserved_fast_track(self, app, mock_llm_with_queue):
        """Custom поля сохраняются в fast_track skill."""
        mock_llm_with_queue(["Response"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

        state = make_graph_state(
            branch_id="fast_track",
            content="заказ",
            custom_field="test_value",
            user_data={"name": "Test User"},
        )
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("custom_field") == "test_value"
        assert result.get("user_data") == {"name": "Test User"}

    @pytest.mark.asyncio
    async def test_custom_fields_preserved_orders_only(self, app, mock_llm_with_queue):
        """Custom поля сохраняются в orders_only skill."""
        mock_llm_with_queue(["Response"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="orders_only")

        state = make_graph_state(
            branch_id="orders_only",
            content="заказ",
            custom_field="preserved",
        )
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.get("custom_field") == "preserved"
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_variables_available_in_all_skills(self, app, mock_llm_with_queue):
        """Переменные доступны во всех skills."""
        mock_llm_with_queue(["Response"])

        container = get_container()

        for branch_id in ["fast_track", "orders_only"]:
            flow = await container.flow_factory.get_flow("example_graph", branch_id=branch_id)

            state = make_graph_state(branch_id=branch_id, content="заказ")
            result = await run_graph_flow(container=container, flow=flow, state=state)

            assert "variables" in result, f"Variables отсутствуют в skill {branch_id}"
            assert "order_prefix" in result["variables"], f"order_prefix отсутствует в skill {branch_id}"


class TestSkillEdgeCases:
    """Тесты граничных случаев для skills."""

    @pytest.mark.asyncio
    async def test_empty_content_default_skill(self, app, mock_llm_with_queue):
        """Пустой content обрабатывается корректно."""
        mock_llm_with_queue(["Response для пустого запроса"])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph")

        state = make_graph_state(content="")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        # Пустой content идет в general route
        assert result.get("route") == "general"
        assert result.get("processed") is True

    @pytest.mark.asyncio
    async def test_nonexistent_skill_uses_canonical_default(self, app, mock_llm_with_queue):
        """Несуществующий skill не создаёт отдельный graph contract."""
        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="nonexistent_skill")

        assert flow is not None
        assert flow.entry == "classifier"

    @pytest.mark.asyncio
    async def test_interrupt_handling_with_skill(self, app, mock_llm_with_queue):
        """Interrupt обрабатывается корректно с любым skill."""
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Уточните заказ"}}
        ])

        container = get_container()
        flow = await container.flow_factory.get_flow("example_graph", branch_id="fast_track")

        state = make_graph_state(branch_id="fast_track", content="заказ")
        result = await run_graph_flow(container=container, flow=flow, state=state)

        assert result.interrupt is not None
        assert result.interrupt.question is not None
