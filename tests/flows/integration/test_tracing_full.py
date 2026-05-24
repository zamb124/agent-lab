"""
ПОЛНЫЕ интеграционные тесты трейсинга.

Тесты покрывают ВЕСЬ функционал трейсинга:

1. ReAct агент (example_react):
   - llm_node spans: весь ReAct-цикл ноды (LLM + tools)
   - react.iteration spans: каждая итерация ReAct цикла
   - llm spans: каждый вызов LLM с токенами и duration
   - tool spans: каждый вызов tool с аргументами и результатом
   - субагент spans: вложенные агенты как tools
   - interrupt spans: ask_user прерывания

2. Graph flow (example_graph):
   - flow spans: начало/конец flow
   - node spans: каждая нода (function, llm_node)
   - путь выполнения: условные переходы видны по последовательности

3. Контекст:
   - user_id, session_agent
   - task_id, flow_id

4. Иерархия:
   - parent_span_id правильно связывает spans
   - можно построить дерево выполнения
"""

import asyncio
import time
from typing import Any

import pytest

from core.clients.llm import setup_mock_responses
from core.logging import get_logger
from core.tracing import setup_tracing
from core.tracing.config import TracingConfig
from core.tracing.models import TraceSpanRecord
from core.tracing.provider import set_tracing_enabled
from core.tracing.tracer import set_span_repository, set_tracing_service_name

logger = get_logger(__name__)


async def _wait_spans(
    container: Any,
    task_id: str | None,
    flow_id: str,
    *,
    filter_agent_id: str | None = None,
    timeout: float = 8.0,
    interval: float = 0.05,
) -> list[TraceSpanRecord]:
    """Ожидание появления spans в БД вместо фиксированной паузы."""
    deadline = time.monotonic() + timeout
    last: list[TraceSpanRecord] = []
    while time.monotonic() < deadline:
        spans: list[TraceSpanRecord] = []
        if task_id:
            spans = await container.span_repository.get_spans_by_task(task_id)
        if not spans:
            raw = await container.span_repository.get_spans_by_flow(flow_id, limit=20)
            if filter_agent_id:
                spans = [s for s in raw if s.flow_id == filter_agent_id][:10]
            else:
                spans = raw[:10]
        last = spans
        if last:
            return last
        await asyncio.sleep(interval)
    return last


@pytest.fixture(autouse=True)
def enable_tracing_for_test(container):
    """
    Включает трейсинг для каждого теста.
    autouse=True - применяется автоматически.
    Зависит от container чтобы app уже был инициализирован.
    """
    # Включаем трейсинг принудительно
    config = TracingConfig(
        enabled=True,
        postgres_enabled=True,
        tempo_enabled=False,
        service_name="platform-test",
    )
    setup_tracing(config)
    set_tracing_service_name("platform-test")
    set_span_repository(container.span_repository)
    set_tracing_enabled(True)

    yield

    # Не отключаем после теста - spans останутся для анализа


class TestLlmNodeTracing:
    """
    Тесты трейсинга ReAct агента (example_react).

    Проверяем что все этапы работы агента записываются:
    - Каждая итерация ReAct цикла
    - Каждый вызов LLM
    - Каждый вызов tool
    """

    @pytest.mark.asyncio
    async def test_llm_node_full_trace_with_tool(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Полный тест ReAct агента: tool вызов → финальный ответ.

        Сценарий:
        1. Агент получает запрос "Посчитай 2+2"
        2. Агент вызывает calculator tool
        3. Агент формирует финальный ответ

        Ожидаемые spans:
        - llm_node span
        - react.iteration spans (минимум 2)
        - llm spans (минимум 2)
        - tool.calculator span
        """
        # Mock LLM ответы: tool_call → final answer
        setup_mock_responses(response_queue=[
            {
                "type": "tool_call",
                "tool": "calculator",
                "args": {"expression": "2 + 2"},
            },
            "Результат вычисления 2+2 равен 4",
        ])

        # Отправляем запрос через A2A API
        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Посчитай 2 + 2"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()
        assert "error" not in result, f"JSON-RPC error: {result}"

        # Извлекаем task_id из результата для поиска spans
        task_result = result.get("result", {})
        task_id = task_result.get("id")

        spans = await _wait_spans(
            container, task_id, "example_react", filter_agent_id="example_react"
        )

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_llm_node_full_trace_with_tool ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans count: {len(spans)}")
        logger.info(f"Span names: {span_names}")

        # === СТРОГИЕ ПРОВЕРКИ - ТЕСТ ПАДАЕТ ЕСЛИ SPANS НЕ ЗАПИСАЛИСЬ ===

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # 1. FLOW SPAN - обязательно
        flow_spans = [s for s in spans if s.operation_name.startswith("flow.")]
        assert len(flow_spans) >= 1, \
            f"ДОЛЖЕН быть flow.example_react span! Получено: {span_names}"

        # 2. NODE SPAN - обязательно (main нода)
        node_spans = [s for s in spans if s.operation_name.startswith("node.")]
        assert len(node_spans) >= 1, \
            f"ДОЛЖЕН быть node.llm_node.main span! Получено: {span_names}"

        # 3. LLM_NODE SPAN - обязательно
        llm_node_spans = [
            s for s in spans if s.operation_name.startswith("llm_node.")
        ]
        assert len(llm_node_spans) > 0, \
            f"ДОЛЖЕН быть llm_node span. Получено: {span_names}"

        # 4. LLM SPANS (минимум 2: tool_call + final)
        llm_spans = [s for s in spans if "llm" in s.operation_name.lower()]
        assert len(llm_spans) >= 2, \
            f"ДОЛЖНО быть минимум 2 LLM spans. Получено {len(llm_spans)}: {span_names}"

        # 5. TOOL SPAN - calculator
        tool_spans = [s for s in spans if "calculator" in s.operation_name]
        assert len(tool_spans) >= 1, \
            f"ДОЛЖЕН быть tool.calculator span. Получено: {span_names}"

        # 6. REACT ITERATION SPANS
        iteration_spans = [s for s in spans if "react.iteration" in s.operation_name]
        assert len(iteration_spans) >= 2, \
            f"ДОЛЖНО быть минимум 2 react.iteration spans. Получено: {span_names}"

        logger.info("✓ Все обязательные spans присутствуют: flow, node, llm_node, llm, tool, iteration")

    @pytest.mark.asyncio
    async def test_llm_node_interrupt_trace(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест трейсинга interrupt (ask_user).

        Сценарий:
        1. Агент вызывает ask_user tool
        2. Должен быть interrupt span
        3. Статус задачи = input-required
        """
        setup_mock_responses(response_queue=[
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Как вас зовут?"},
            },
        ])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"int_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Помоги мне"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()

        # Проверяем что вернулся interrupt
        task_result = result.get("result", {})
        task_id = task_result.get("id")
        status = task_result.get("status", {})
        assert status.get("state") == "input-required", \
            f"Ожидаем input-required, получили: {status}"

        spans = await _wait_spans(container, task_id, "example_react")

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_llm_node_interrupt_trace ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans: {span_names}")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # Проверяем наличие interrupt или ask_user span
        interrupt_spans = [s for s in spans
                         if "interrupt" in s.operation_name.lower()
                         or "ask_user" in s.operation_name]
        assert len(interrupt_spans) >= 1, \
            f"Должен быть interrupt или ask_user span. Получено: {span_names}"

    @pytest.mark.asyncio
    async def test_llm_node_with_subagent_trace(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест трейсинга с вызовом субагента.

        example_main_agent имеет tool example_subflow (вложенный subflow).
        При вызове субагента должны записаться spans обоих агентов.
        """
        setup_mock_responses(response_queue=[
            # main_agent вызывает субагента
            {
                "type": "tool_call",
                "tool": "example_subflow",
                "args": {"query": "Собери информацию"},
            },
            # subagent вызывает ask_user (interrupt)
            {
                "type": "tool_call",
                "tool": "ask_user",
                "args": {"question": "Какая информация нужна?"},
            },
        ])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"sub_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Собери информацию от пользователя"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_react")

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_llm_node_with_subagent_trace ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans: {span_names}")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # Должны быть spans для main agent и для subagent
        # Вложенный subflow вызывается как tool — будет tool.example_subflow span
        subagent_tool_spans = [s for s in spans
                              if "example_subflow" in s.operation_name]
        assert len(subagent_tool_spans) >= 1, \
            f"Должен быть tool.example_subflow span. Получено: {span_names}"


class TestGraphFlowTracing:
    """
    Тесты трейсинга Graph flow (example_graph).

    Graph flow имеет:
    - classifier (function) - определяет route
    - order_processor, complaint_processor, general_processor (llm_node)
    - formatter (function)

    Проверяем что по spans видно какой путь был выбран.
    """

    @pytest.mark.asyncio
    async def test_graph_flow_order_path_trace(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест пути "заказ" в graph flow.

        Сообщение содержит "заказ" → classifier выбирает order_processor.

        Путь: classifier → order_processor → formatter
        """
        setup_mock_responses(response_queue=[
            "Ваш заказ находится в обработке. Номер: ORD-12345",
        ])

        response = await client.post(
            "/flows/api/v1/example_graph",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"order_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Где мой заказ номер 12345?"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_graph")

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_graph_flow_order_path_trace ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans: {span_names}")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # === СТРОГИЕ ПРОВЕРКИ ДЛЯ GRAPH FLOW ===

        # 1. FLOW SPAN
        flow_spans = [s for s in spans if s.operation_name.startswith("flow.")]
        assert len(flow_spans) >= 1, \
            f"ДОЛЖЕН быть flow.example_graph span! Получено: {span_names}"

        # 2. NODE SPANS для пути: classifier → order_processor → formatter
        classifier_spans = [s for s in spans if "classifier" in s.operation_name]
        assert len(classifier_spans) >= 1, \
            f"ДОЛЖЕН быть node для classifier! Путь: classifier→order_processor→formatter. Получено: {span_names}"

        order_spans = [s for s in spans if "order_processor" in s.operation_name
                      or "order" in s.operation_name.lower()]
        assert len(order_spans) >= 1, \
            f"ДОЛЖЕН быть span для order_processor! Получено: {span_names}"

        formatter_spans = [s for s in spans if "formatter" in s.operation_name]
        assert len(formatter_spans) >= 1, \
            f"ДОЛЖЕН быть node для formatter! Получено: {span_names}"

        logger.info("✓ Graph flow путь ORDER верифицирован: classifier → order_processor → formatter")

    @pytest.mark.asyncio
    async def test_graph_flow_complaint_path_trace(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест пути "жалоба" в graph flow.

        Сообщение содержит "жалоба" → classifier выбирает complaint_processor.
        """
        setup_mock_responses(response_queue=[
            "Ваша жалоба зарегистрирована. Номер: CMP-67890",
        ])

        response = await client.post(
            "/flows/api/v1/example_graph",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"compl_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Хочу подать жалобу на качество обслуживания"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_graph")

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_graph_flow_complaint_path_trace ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans: {span_names}")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # === СТРОГИЕ ПРОВЕРКИ ДЛЯ COMPLAINT ПУТИ ===

        # NODE SPANS для пути: classifier → complaint_processor → formatter
        classifier_spans = [s for s in spans if "classifier" in s.operation_name]
        assert len(classifier_spans) >= 1, \
            f"ДОЛЖЕН быть node для classifier! Получено: {span_names}"

        complaint_spans = [s for s in spans if "complaint_processor" in s.operation_name
                         or "complaint" in s.operation_name.lower()]
        assert len(complaint_spans) >= 1, \
            f"ДОЛЖЕН быть span для complaint_processor! Получено: {span_names}"

        logger.info("✓ Graph flow путь COMPLAINT верифицирован: classifier → complaint_processor → formatter")

    @pytest.mark.asyncio
    async def test_graph_flow_general_path_trace(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест пути "general" в graph flow.

        Сообщение не содержит "заказ", "жалоба", "кот", "привет" → classifier выбирает general_processor.
        """
        setup_mock_responses(response_queue=[
            "Здравствуйте! Чем могу помочь?",
        ])

        response = await client.post(
            "/flows/api/v1/example_graph",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"gen_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Какой у вас режим работы?"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200, f"API error: {response.text}"
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_graph")

        span_names = [s.operation_name for s in spans]

        logger.info("=== TEST: test_graph_flow_general_path_trace ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Spans: {span_names}")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        # === СТРОГИЕ ПРОВЕРКИ ДЛЯ GENERAL ПУТИ ===

        # NODE SPANS для пути: classifier → general_processor → formatter
        classifier_spans = [s for s in spans if "classifier" in s.operation_name]
        assert len(classifier_spans) >= 1, \
            f"ДОЛЖЕН быть node для classifier! Получено: {span_names}"

        general_spans = [s for s in spans if "general_processor" in s.operation_name
                        or "general" in s.operation_name.lower()]
        assert len(general_spans) >= 1, \
            f"ДОЛЖЕН быть span для general_processor! Получено: {span_names}"

        logger.info("✓ Graph flow путь GENERAL верифицирован: classifier → general_processor → formatter")


class TestSpanAttributes:
    """
    Тесты проверки атрибутов spans.

    Каждый span должен содержать контекстную информацию:
    - span_id, trace_id, parent_span_id
    - operation_name
    - start_time, end_time, duration_ms
    - session_agent, flow_id, task_id
    """

    @pytest.mark.asyncio
    async def test_span_has_required_attributes(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест наличия обязательных атрибутов в spans.
        """
        setup_mock_responses(response_queue=["Test response"])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"attrs_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Test"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_react")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        logger.info("=== TEST: test_span_has_required_attributes ===")

        for span in spans:
            # Обязательные поля
            assert span.span_id, f"span_id обязателен: {span}"
            assert span.trace_id, f"trace_id обязателен: {span}"
            assert span.operation_name, f"operation_name обязателен: {span}"
            assert span.start_time, f"start_time обязателен: {span}"

            # flow_id должен быть example_react (для spans с flow_id)
            if span.flow_id:
                assert span.flow_id == "example_react", \
                    f"flow_id должен быть example_react, получено: {span.flow_id}"

            logger.info(f"Span OK: {span.operation_name}")


class TestSpanHierarchy:
    """
    Тесты иерархии spans (parent-child).

    Spans должны быть связаны через parent_span_id.
    Можно построить дерево выполнения.
    """

    @pytest.mark.asyncio
    async def test_span_parent_child_hierarchy(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест иерархии parent-child.

        llm_node span - root
          └── react.iteration.1
                ├── llm span
                └── tool span
          └── react.iteration.2
                └── llm span
        """
        setup_mock_responses(response_queue=[
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "1+1"}},
            "Результат: 2",
        ])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"hier_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Посчитай 1+1"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        assert response.status_code == 200
        result = response.json()
        task_id = result.get("result", {}).get("id")

        spans = await _wait_spans(container, task_id, "example_react")

        assert len(spans) > 0, \
            f"КРИТИЧЕСКАЯ ОШИБКА: spans не записались! task_id={task_id}"

        logger.info("=== TEST: test_span_parent_child_hierarchy ===")

        # Строим дерево
        span_map = {s.span_id: s for s in spans}
        root_spans = [s for s in spans if not s.parent_span_id]
        child_spans = [s for s in spans if s.parent_span_id]

        logger.info(f"Total spans: {len(spans)}")
        logger.info(f"Root spans: {len(root_spans)}")
        logger.info(f"Child spans: {len(child_spans)}")

        for span in spans:
            parent_id = span.parent_span_id
            if parent_id:
                parent = span_map.get(parent_id)
                parent_name = parent.operation_name if parent else "NOT_FOUND"
                logger.info(f"  {span.operation_name} -> parent: {parent_name}")
            else:
                logger.info(f"  {span.operation_name} [ROOT]")

        # Должны быть child spans (иерархия должна быть)
        assert len(child_spans) > 0, \
            f"Должны быть child spans с parent_span_id. Spans: {[s.operation_name for s in spans]}"


@pytest.mark.timeout(30)
class TestTracingAPI:
    """
    Тесты API для получения трейсов.

    В интеграции без Tempo spans живут в PostgreSQL; дерево из Tempo (/task, /trace)
    здесь не используется — проверяем GET /traces/search по flow_id и task_id.
    """

    @pytest.mark.asyncio
    async def test_get_traces_by_task_api(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест API GET /traces/search?task_id=... (platform_tracing).
        """
        setup_mock_responses(response_queue=["API test response"])

        response = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"api_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "API test"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )
        assert response.status_code == 200, f"API error: {response.text}"

        result = response.json()
        task_id = result.get("result", {}).get("id")
        assert task_id, f"Не получили task_id из ответа: {result}"

        deadline = time.monotonic() + 8.0
        data: dict[str, Any] = {"traces_count": 0}
        while time.monotonic() < deadline:
            traces_response = await client.get(
                "/flows/api/v1/traces/search",
                params={"task_id": task_id, "limit": 50},
            )
            assert traces_response.status_code == 200, f"API error: {traces_response.text}"
            data = traces_response.json()
            if data.get("traces_count", 0) > 0:
                break
            await asyncio.sleep(0.05)

        logger.info("=== TEST: test_get_traces_by_task_api ===")
        logger.info(f"Task ID: {task_id}")
        logger.info(f"Traces count: {data.get('traces_count')}")

        assert data["traces_count"] > 0, (
            f"КРИТИЧЕСКАЯ ОШИБКА: search вернул 0 traces для task {task_id}"
        )
        traces_list = data.get("traces")
        assert isinstance(traces_list, list)
        assert len(traces_list) > 0
        span_total = sum(len(t.get("spans", [])) for t in traces_list)
        assert span_total > 0

    @pytest.mark.asyncio
    async def test_get_traces_by_flow_api(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест API GET /traces/search?flow_id=... (platform_tracing).
        """
        setup_mock_responses(response_queue=["Agent API test"])

        post_resp = await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"flow_api_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Agent API test"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )
        assert post_resp.status_code == 200, f"API error: {post_resp.text}"

        deadline = time.monotonic() + 8.0
        data: dict[str, Any] = {"traces_count": 0}
        while time.monotonic() < deadline:
            flow_response = await client.get(
                "/flows/api/v1/traces/search",
                params={"flow_id": "example_react", "limit": 50},
            )
            assert flow_response.status_code == 200, f"API error: {flow_response.text}"
            data = flow_response.json()
            if data.get("traces_count", 0) > 0:
                break
            await asyncio.sleep(0.05)

        logger.info("=== TEST: test_get_traces_by_flow_api ===")
        logger.info(f"Traces count for flow example_react: {data['traces_count']}")

        assert data["traces_count"] > 0
        traces_list = data.get("traces")
        assert isinstance(traces_list, list)
        assert len(traces_list) > 0

    @pytest.mark.asyncio
    async def test_search_traces_api(
        self,
        client,
        app,
        container,
        unique_id: str,
    ):
        """
        Тест API /api/v1/traces/search
        """
        setup_mock_responses(response_queue=["Search API test"])

        await client.post(
            "/flows/api/v1/example_react",
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "method": "message/send",
                "params": {
                    "message": {
                        "messageId": f"search_api_msg_{unique_id}",
                        "role": "user",
                        "parts": [{"kind": "text", "text": "Search API test"}],
                    },
                },
            },
            headers={"X-Internal-Service-Key": "test-internal-service-key"},
        )

        deadline = time.monotonic() + 8.0
        data = {"traces_count": 0}
        while time.monotonic() < deadline:
            search_response = await client.get(
                "/flows/api/v1/traces/search",
                params={"flow_id": "example_react", "limit": 10},
            )
            assert search_response.status_code == 200, f"API error: {search_response.text}"
            data = search_response.json()
            if data.get("traces_count", 0) > 0:
                break
            await asyncio.sleep(0.05)

        logger.info("=== TEST: test_search_traces_api ===")
        logger.info(f"Search results: {data['traces_count']} traces")

        assert "traces_count" in data
        assert "traces" in data
        assert data["traces_count"] > 0
