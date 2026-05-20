"""
Интеграционные тесты для Breakpoints.

Проверяют что breakpoints работают корректно для различных типов агентов:
- example_react: ReAct агент с tools и субагентами
- example_graph: Графовый flow с function нодами и условными переходами

ВАЖНО:
- Breakpoints аналогичны interrupt (ask_user), но:
  1. Срабатывают ПЕРЕД выполнением ноды
  2. Сохраняют полный snapshot state
  3. Продолжение выполнения через continue (не через новый content)
- Единственный мок - MockLLM
- Все остальное реальное: state, flow, nodes, tools
"""


import pytest
import pytest_asyncio

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig
from apps.flows.src.runtime.flow import Flow
from core.state import ExecutionState


class TestBreakpointsReactAgent:
    """Тесты breakpoints для example_react ReAct агента."""

    @pytest_asyncio.fixture
    async def flow_config(self, app) -> FlowConfig:
        """Загружает конфиг example_react из БД."""
        container = get_container()
        config = await container.flow_repository.get("example_react")
        assert config is not None, "Agent example_react не найден в БД"
        return config

    @pytest_asyncio.fixture
    async def flow(self, app) -> Flow:
        """Создаёт Agent из example_react."""
        container = get_container()
        return await container.flow_factory.get_flow("example_react")

    @pytest.mark.asyncio
    async def test_breakpoint_stops_at_entry_node(self, flow, mock_llm_with_queue):
        """
        Breakpoint на entry ноде останавливает выполнение ПЕРЕД её запуском.

        Сценарий:
        1. Устанавливаем breakpoint на "main" (entry)
        2. Запускаем агента
        3. Проверяем что выполнение остановилось БЕЗ вызова LLM
        4. state.breakpoint_hit == "main"
        5. state.breakpoint_state содержит snapshot
        """
        mock_llm_with_queue([
            # Этот ответ НЕ должен быть использован - breakpoint срабатывает ДО ноды
            "Это не должно появиться"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет!",
            breakpoints={"main": True},  # Breakpoint на entry ноде
        )

        result = await flow.run(state)

        # Breakpoint сработал
        assert result.breakpoint_hit == "main", \
            f"Breakpoint должен сработать на 'main', но breakpoint_hit={result.breakpoint_hit}"

        # Snapshot state сохранён
        assert result.breakpoint_state is not None, \
            "breakpoint_state должен содержать snapshot"
        assert result.breakpoint_state.get("content") == "Привет!", \
            "Snapshot должен содержать исходный content"

        # current_nodes указывает на ноду breakpoint
        assert result.current_nodes == ["main"], \
            f"current_nodes должен быть ['main'], но {result.current_nodes}"

        # LLM НЕ был вызван (response пуст)
        assert result.response is None, \
            "Response должен быть None - LLM не вызывался"

    @pytest.mark.asyncio
    async def test_breakpoint_preserves_state_for_inspection(self, flow, mock_llm_with_queue):
        """
        Breakpoint сохраняет полный snapshot state для инспекции.

        Проверяем что все поля доступны в breakpoint_state.
        """
        mock_llm_with_queue([])

        state = ExecutionState(
            task_id="task-bp-1",
            context_id="context-bp-1",
            user_id="user-bp-1",
            session_id="test-agent:context-bp-1",
            content="Тестовое сообщение",
            variables={"custom_var": "custom_value"},
            breakpoints={"main": True},
        )

        result = await flow.run(state)

        snapshot = result.breakpoint_state
        assert snapshot is not None

        # Проверяем ключевые поля в snapshot
        assert snapshot["task_id"] == "task-bp-1"
        assert snapshot["context_id"] == "context-bp-1"
        assert snapshot["user_id"] == "user-bp-1"
        assert snapshot["content"] == "Тестовое сообщение"
        assert snapshot["variables"]["custom_var"] == "custom_value"

        # Breakpoints сами тоже в snapshot
        assert snapshot["breakpoints"]["main"] is True

    @pytest.mark.asyncio
    async def test_continue_after_breakpoint_resumes_execution(self, flow, mock_llm_with_queue):
        """
        После breakpoint можно продолжить выполнение.

        Сценарий:
        1. Breakpoint на "main"
        2. Выполняем - останавливаемся
        3. Продолжаем - breakpoint_hit сбрасывается автоматически при повторном выполнении
        4. Агент выполняется и возвращает ответ

        ВАЖНО: breakpoint_hit НЕ очищается вручную.
        Логика _check_breakpoint видит что breakpoint_hit == node_id,
        значит мы продолжаем после breakpoint и пропускает проверку.
        """
        mock_llm_with_queue([
            "Привет! Я ваш ассистент."
        ])

        # Шаг 1: Запуск с breakpoint
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет!",
            breakpoints={"main": True},
        )

        result = await flow.run(state)
        assert result.breakpoint_hit == "main"

        # Шаг 2: Continue - НЕ очищаем breakpoint_hit!
        # breakpoint_hit остаётся == "main", это сигнал что мы продолжаем с этой ноды
        # breakpoint_state можно очистить для экономии памяти
        result.breakpoint_state = None

        # Шаг 3: Продолжаем выполнение
        final_result = await flow.run(result)

        # Агент завершился с ответом
        assert final_result.response is not None, \
            "После continue агент должен вернуть response"
        assert "ассистент" in final_result.response.lower() or "привет" in final_result.response.lower(), \
            f"Response должен содержать ответ агента: {final_result.response}"

        # breakpoint_hit очищен самой логикой _check_breakpoint
        assert final_result.breakpoint_hit is None

    @pytest.mark.asyncio
    async def test_breakpoint_with_tool_call(self, flow, mock_llm_with_queue):
        """
        Breakpoint работает вместе с tool calls.

        Сценарий:
        1. Агент вызывает calculator
        2. Возвращает финальный ответ
        3. Breakpoint на entry останавливает ДО всего этого
        """
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "10 + 5"}},
            "Результат: 15"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Сколько будет 10 + 5?",
            breakpoints={"main": True},
        )

        result = await flow.run(state)

        # Breakpoint сработал ДО выполнения
        assert result.breakpoint_hit == "main"
        assert result.response is None
        assert "calculator" not in result.tool_results

    @pytest.mark.asyncio
    async def test_breakpoint_and_interrupt_are_independent(self, flow, mock_llm_with_queue, sync_tools):
        """
        Breakpoint и interrupt (ask_user) - независимые механизмы.

        Сценарий:
        1. Breakpoint на main
        2. Continue (breakpoint_hit остаётся для сигнала continue)
        3. Агент вызывает ask_user - interrupt
        4. Проверяем что оба механизма работают корректно
        """
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
        ])

        # Шаг 1: Breakpoint
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Начать",
            breakpoints={"main": True},
        )

        result = await flow.run(state)
        assert result.breakpoint_hit == "main"
        assert result.interrupt is None, "Interrupt не должен быть до continue"

        # Шаг 2: Continue - НЕ очищаем breakpoint_hit!
        # breakpoint_hit остаётся == "main" как сигнал для продолжения
        result.breakpoint_state = None

        result = await flow.run(result)

        # Шаг 3: Interrupt от ask_user
        assert result.interrupt is not None, "Должен быть interrupt от ask_user"
        assert "зовут" in result.interrupt.question.lower()
        # breakpoint_hit был очищен логикой _check_breakpoint
        assert result.breakpoint_hit is None, "breakpoint_hit должен быть None после interrupt"


class TestBreakpointsGraphAgent:
    """Тесты breakpoints для example_graph графового flow."""

    @pytest_asyncio.fixture
    async def flow_config(self, app) -> FlowConfig:
        """Загружает конфиг example_graph из БД."""
        container = get_container()
        config = await container.flow_repository.get("example_graph")
        assert config is not None, "Agent example_graph не найден в БД"
        return config

    @pytest_asyncio.fixture
    async def flow(self, app) -> Flow:
        """Создаёт Agent из example_graph."""
        container = get_container()
        return await container.flow_factory.get_flow("example_graph")

    @pytest.mark.asyncio
    async def test_breakpoint_on_classifier_function_node(self, flow, mock_llm_with_queue):
        """
        Breakpoint на function ноде (classifier) останавливает выполнение.

        classifier - function нода которая определяет route.
        """
        mock_llm_with_queue([])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Хочу узнать про мой заказ",
            breakpoints={"classifier": True},
        )

        result = await flow.run(state)

        # Breakpoint сработал на classifier
        assert result.breakpoint_hit == "classifier"
        assert result.current_nodes == ["classifier"]

        # route ещё не установлен (classifier не выполнился)
        assert result.get("route") is None

    @pytest.mark.asyncio
    async def test_breakpoint_after_classifier_on_processor(self, flow, mock_llm_with_queue):
        """
        Breakpoint на order_processor после classifier.

        Сценарий:
        1. classifier выполняется, устанавливает route='order'
        2. breakpoint на order_processor останавливает выполнение
        3. Проверяем что route установлен, но LLM не вызван
        """
        mock_llm_with_queue([
            # Этот ответ НЕ должен быть использован
            "Не должно появиться"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Хочу узнать про мой заказ",
            breakpoints={"order_processor": True},
        )

        result = await flow.run(state)

        # classifier выполнился
        assert result.get("route") == "order", \
            f"route должен быть 'order', но {result.get('route')}"

        # breakpoint на order_processor
        assert result.breakpoint_hit == "order_processor"
        assert result.current_nodes == ["order_processor"]

        # LLM не вызван (response пуст)
        assert result.response is None

    @pytest.mark.asyncio
    async def test_breakpoint_on_formatter_after_processor(self, flow, mock_llm_with_queue):
        """
        Breakpoint на formatter после order_processor.

        Сценарий:
        1. classifier -> order -> order_total -> breakpoint на formatter
        2. Проверяем что order_processor выполнился, но formatter нет
        """
        mock_llm_with_queue([
            "Ваш заказ ORD-12345 в обработке."
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Где мой заказ?",
            breakpoints={"formatter": True},
        )

        result = await flow.run(state)

        # classifier и order_processor выполнились
        assert result.get("route") == "order"
        assert result.response is not None, "order_processor должен вернуть response"

        # breakpoint на formatter
        assert result.breakpoint_hit == "formatter"

        # processed ещё не установлен (formatter не выполнился)
        assert result.get("processed") is None

    @pytest.mark.asyncio
    async def test_continue_graph_after_breakpoint(self, flow, mock_llm_with_queue):
        """
        После breakpoint граф продолжает выполнение.

        Сценарий:
        1. Breakpoint на formatter
        2. Continue (breakpoint_hit остаётся как сигнал)
        3. formatter выполняется, добавляет prefix и processed=True
        """
        mock_llm_with_queue([
            "Ваш заказ ORD-12345 в обработке."
        ])

        # Шаг 1: Breakpoint на formatter
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Где мой заказ?",
            breakpoints={"formatter": True},
        )

        result = await flow.run(state)
        assert result.breakpoint_hit == "formatter"
        assert result.get("processed") is None

        # Шаг 2: Continue - НЕ очищаем breakpoint_hit!
        # breakpoint_hit остаётся == "formatter" как сигнал для продолжения
        result.breakpoint_state = None

        final_result = await flow.run(result)

        # formatter выполнился
        assert final_result.get("processed") is True
        assert "[ORDER]" in final_result.get("response", ""), \
            f"Response должен содержать [ORDER] prefix: {final_result.get('response')}"

    @pytest.mark.asyncio
    async def test_multiple_breakpoints_sequential(self, flow, mock_llm_with_queue):
        """
        Несколько breakpoints срабатывают последовательно.

        Сценарий:
        1. Breakpoint на classifier
        2. Continue -> classifier выполняется -> breakpoint на order_processor
        3. Continue -> order_processor выполняется -> breakpoint на formatter
        4. Continue -> formatter выполняется -> завершение

        ВАЖНО: breakpoint_hit НЕ очищается вручную!
        При продолжении логика видит breakpoint_hit == текущая нода,
        пропускает проверку, выполняет ноду, и переходит к следующей.
        """
        mock_llm_with_queue([
            "Ваш заказ обрабатывается."
        ])

        # Шаг 1: Все breakpoints активны
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Хочу узнать про заказ",
            breakpoints={
                "classifier": True,
                "order_processor": True,
                "formatter": True,
            },
        )

        # Breakpoint 1: classifier
        result = await flow.run(state)
        assert result.breakpoint_hit == "classifier"

        # Continue -> classifier выполняется -> Breakpoint 2: order_processor
        # НЕ очищаем breakpoint_hit! Он остаётся как сигнал продолжения.
        result.breakpoint_state = None
        result = await flow.run(result)
        assert result.breakpoint_hit == "order_processor", \
            f"После continue с classifier должен быть breakpoint на order_processor, но {result.breakpoint_hit}"
        assert result.get("route") == "order"

        # Continue -> order_processor выполняется -> Breakpoint 3: formatter
        result.breakpoint_state = None
        result = await flow.run(result)
        assert result.breakpoint_hit == "formatter", \
            f"После continue с order_processor должен быть breakpoint на formatter, но {result.breakpoint_hit}"
        assert result.response is not None

        # Continue -> formatter выполняется -> Завершение
        result.breakpoint_state = None
        final_result = await flow.run(result)

        assert final_result.breakpoint_hit is None
        assert final_result.get("processed") is True

    @pytest.mark.asyncio
    async def test_breakpoint_on_complaint_route(self, flow, mock_llm_with_queue):
        """
        Breakpoint на complaint_processor при маршруте complaint.
        """
        mock_llm_with_queue([
            "Ваша жалоба CMP-67890 зарегистрирована."
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="У меня жалоба на сервис",
            breakpoints={"complaint_processor": True},
        )

        result = await flow.run(state)

        # classifier определил route = complaint
        assert result.get("route") == "complaint"

        # breakpoint на complaint_processor
        assert result.breakpoint_hit == "complaint_processor"
        assert result.response is None


class TestBreakpointsStateManagement:
    """Тесты управления state для breakpoints."""

    @pytest_asyncio.fixture
    async def flow(self, app) -> Flow:
        """Создаёт Agent из example_react."""
        container = get_container()
        return await container.flow_factory.get_flow("example_react")

    @pytest.mark.asyncio
    async def test_breakpoint_state_snapshot_is_immutable(self, flow, mock_llm_with_queue):
        """
        Snapshot state в breakpoint_state не меняется после continue.
        """
        mock_llm_with_queue([
            "Ответ агента"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Оригинальный контент",
            breakpoints={"main": True},
        )

        result = await flow.run(state)

        # Сохраняем snapshot
        snapshot_content = result.breakpoint_state["content"]
        assert snapshot_content == "Оригинальный контент"

        # Меняем state после breakpoint
        result.content = "Изменённый контент"

        # Snapshot остался неизменным
        assert result.breakpoint_state["content"] == "Оригинальный контент"

    @pytest.mark.asyncio
    async def test_disabled_breakpoint_does_not_stop(self, flow, mock_llm_with_queue):
        """
        Отключённый breakpoint (False) не останавливает выполнение.
        """
        mock_llm_with_queue([
            "Нормальный ответ"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Привет",
            breakpoints={"main": False},  # Отключён
        )

        result = await flow.run(state)

        # Breakpoint не сработал
        assert result.breakpoint_hit is None
        assert result.breakpoint_state is None

        # Агент выполнился
        assert result.response is not None

    @pytest.mark.asyncio
    async def test_empty_breakpoints_does_not_affect_execution(self, flow, mock_llm_with_queue):
        """
        Пустой dict breakpoints не влияет на выполнение.
        """
        mock_llm_with_queue([
            "Обычный ответ"
        ])

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="Тест",
            breakpoints={},  # Пустой
        )

        result = await flow.run(state)

        assert result.breakpoint_hit is None
        assert result.response is not None


@pytest.mark.real_taskiq
class TestBreakpointsAPIIntegration:
    """
    Тесты breakpoints через API.

    Проверяют полный путь: API -> A2AChannel -> TaskIQ -> Agent.
    Используют реальный TaskIQ worker.
    """

    @pytest.fixture(autouse=True)
    def require_taskiq_worker(self, taskiq_worker):
        """Все тесты требуют TaskIQ worker."""
        pass

    @pytest_asyncio.fixture
    async def setup_breakpoint_flow(self, app, container, unique_id, mock_context):
        """Создает простой flow для тестов breakpoints."""
        from apps.flows.src.models import FlowConfig
        from core.context import set_context

        # Устанавливаем company context перед созданием flow
        set_context(mock_context)

        flow_id = f"bp_api_test_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Breakpoint API Test Agent",
            entry="step1",
            nodes={
                "step1": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['step1_done'] = True\n    return state",
                },
                "step2": {
                    "type": "code",
                    "code": "async def run(args, state):\n    state['step2_done'] = True\n    state['response'] = 'All done'\n    return state",
                },
            },
            edges=[
                {"from": "step1", "to": "step2"},
                {"from": "step2", "to": None},
            ],
        )
        await container.flow_repository.set(flow_config)
        return flow_id

    @pytest.mark.asyncio
    async def test_breakpoint_via_taskiq_stops_execution(
        self, app, container, setup_breakpoint_flow, unique_id, mock_context
    ):
        """
        Breakpoint через TaskIQ останавливает выполнение.

        Проверяет что breakpoints из metadata передаются через весь путь:
        API -> process_flow_task -> process_task -> ExecutionState -> Agent
        """
        from apps.flows.src.tasks.flow_tasks import process_flow_task

        flow_id = setup_breakpoint_flow
        session_id = f"{flow_id}:bp-taskiq-{unique_id}"

        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"

        # Кикаем задачу с breakpoint на step2
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            metadata={"breakpoints": {"step2": True}},
            context_data=mock_context.model_dump(),
        )

        result = await task.wait_result()

        assert not result.is_err, f"Task failed: {result.error}"
        # Должен остановиться на breakpoint (статус input-required с breakpoint_hit)
        status = result.return_value.get("status")
        assert status == "input-required", \
            f"Expected input-required for breakpoint, got status='{status}', full: {result.return_value}"
        assert result.return_value.get("breakpoint_hit") == "step2"

    @pytest.mark.asyncio
    async def test_breakpoint_via_a2a_endpoint(
        self, client, setup_breakpoint_flow, unique_id
    ):
        """
        Breakpoint через A2A endpoint останавливает выполнение.
        """
        flow_id = setup_breakpoint_flow
        context_id = f"a2a-bp-{unique_id}"
        message_id = f"msg-{unique_id}"
        jsonrpc_id = f"req-{unique_id}"

        response = await client.post(
            f"/flows/api/v1/{flow_id}",
            json={
                "jsonrpc": "2.0",
                "id": jsonrpc_id,
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": message_id,
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Start"}],
                        "contextId": context_id,
                    },
                    "metadata": {
                        "breakpoints": {"step1": True}
                    }
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "result" in data, f"Expected result in response: {data}"

        # Проверяем что breakpoint сработал (статус input-required с metadata.breakpoint=true)
        task_status = data["result"]["status"]
        assert task_status["state"] == "input-required", \
            f"Expected input-required for breakpoint, got: {task_status}"

    @pytest.mark.asyncio
    async def test_continue_after_breakpoint_via_taskiq(
        self, app, container, setup_breakpoint_flow, unique_id, mock_context
    ):
        """
        После breakpoint можно продолжить выполнение через TaskIQ.
        """
        from apps.flows.src.tasks.flow_tasks import process_flow_task

        flow_id = setup_breakpoint_flow
        session_id = f"{flow_id}:bp-continue-{unique_id}"

        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"

        # Шаг 1: Останавливаемся на breakpoint
        task1 = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            metadata={"breakpoints": {"step2": True}},
            context_data=mock_context.model_dump(),
        )

        result1 = await task1.wait_result()
        assert not result1.is_err
        assert result1.return_value.get("status") == "input-required", \
            f"Expected input-required, got: {result1.return_value}"
        assert result1.return_value.get("breakpoint_hit") == "step2"

        # Шаг 2: Продолжаем выполнение (is_resume=True)
        # Breakpoint сохранён в state, при resume он будет пропущен
        task2 = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="",  # Пустой content для continue
            is_resume=True,
            metadata={"breakpoints": {"step2": True}},  # Breakpoints остаются
            context_data=mock_context.model_dump(),
        )

        result2 = await task2.wait_result()

        assert not result2.is_err, f"Resume failed: {result2.error}"
        assert result2.return_value.get("status") == "completed", \
            f"Expected completed, got: {result2.return_value}"
        assert "All done" in result2.return_value.get("response", "")

    @pytest.mark.asyncio
    async def test_breakpoint_on_entry_node_via_api(
        self, client, setup_breakpoint_flow, unique_id
    ):
        """
        Breakpoint на entry ноде останавливает выполнение ДО любой логики.
        """
        flow_id = setup_breakpoint_flow
        context_id = f"api-bp-entry-{unique_id}"
        session_id = f"{flow_id}:{context_id}"

        response = await client.post(
            "/flows/api/v1/tasks/submit",
            json={
                "flow_id": flow_id,
                "content": "Test",
                "session_id": session_id,
                "metadata": {
                    "breakpoints": {"step1": True}
                }
            },
        )

        assert response.status_code == 200
        data = response.json()

        # Проверяем что breakpoint сработал на entry ноде (input-required)
        assert data["status"]["state"] == "input-required", \
            f"Expected input-required for breakpoint, got: {data['status']}"

    @pytest.mark.asyncio
    async def test_no_breakpoint_completes_normally(
        self, app, container, setup_breakpoint_flow, unique_id, mock_context
    ):
        """
        Без breakpoints агент выполняется до конца.
        """
        from apps.flows.src.tasks.flow_tasks import process_flow_task

        flow_id = setup_breakpoint_flow
        session_id = f"{flow_id}:bp-none-{unique_id}"

        mock_context.session_id = session_id
        mock_context.flow_id = flow_id
        mock_context.user.user_id = "test-user"

        # Кикаем задачу БЕЗ breakpoints
        task = await process_flow_task.kiq(
            flow_id=flow_id,
            session_id=session_id,
            user_id="test-user",
            content="Start",
            metadata={},  # Нет breakpoints
            context_data=mock_context.model_dump(),
        )

        result = await task.wait_result()

        assert not result.is_err
        assert result.return_value.get("status") == "completed"
        assert "All done" in result.return_value.get("response", "")
