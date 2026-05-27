"""
E2E тесты для FlowInterrupt с реальным TaskIQ worker.

Тестируют:
1. Interrupt в простом tool (ask_user)
2. Interrupt в субагенте (llm_node как tool)
3. Множественные interrupts с сохранением истории
4. Resume передает ответ в правильный субагент

БЕЗ МОКОВ - используют реальный LLM и TaskIQ worker.
"""

import pytest
import pytest_asyncio

from apps.flows.src.container import get_container
from core.state import ExecutionState
from tests.flows.durable_runtime_harness import run_flow


@pytest.mark.real_taskiq
class TestInterruptE2E:
    """E2E тесты interrupt с реальным worker."""

    @pytest_asyncio.fixture
    async def agent_flow(self, app):
        """Загружает example_react flow."""
        container = get_container()
        flow = await container.flow_factory.get_flow("example_react")
        return flow

    @pytest.mark.asyncio
    async def test_simple_ask_user_interrupt(self, agent_flow, mock_llm_with_queue, unique_id):
        """
        Простой interrupt от ask_user tool.

        Сценарий:
        1. LLM вызывает ask_user
        2. Агент возвращает state с interrupt
        3. Resume с ответом пользователя
        4. LLM формирует финальный ответ
        """
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
                "Приятно познакомиться, Иван!",
            ]
        )
        context_id = f"e2e-context-1-{unique_id}"
        state = ExecutionState(
            task_id=f"e2e-test-1-{unique_id}",
            context_id=context_id,
            user_id="test-user",
            session_id=f"{agent_flow.flow_id}:{context_id}",
            content="Привет",
        )
        result = await run_flow(container=agent_flow.container, flow=agent_flow, state=state)
        assert result.interrupt is not None, "Должен быть interrupt"
        assert "зовут" in result.interrupt.question.lower()
        assert len(result.interrupt_path) > 0, "interrupt_path не должен быть пустым"
        result.content = "Иван"
        final_result = await run_flow(container=agent_flow.container, flow=agent_flow, state=result)
        assert final_result.interrupt is None, "После resume interrupt должен быть None"
        assert final_result.response is not None, "Должен быть response"
        assert "иван" in final_result.response.lower()

    @pytest.mark.asyncio
    async def test_subagent_interrupt_and_resume(self, agent_flow, mock_llm_with_queue, unique_id):
        """
        Interrupt в субагенте (llm_node как tool).

        Сценарий:
        1. Главный агент вызывает example_subflow
        2. Субагент вызывает ask_user
        3. State сохраняется в nested_states
        4. Resume передает ответ в субагента
        5. Субагент отвечает
        6. Главный агент формирует финальный ответ
        """
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "example_subflow",
                    "args": {"query": "найти магазин"},
                },
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                "Магазин на Тверской, Москва.",
                "Рекомендую магазин на Тверской!",
            ]
        )
        context_id = f"e2e-context-2-{unique_id}"
        state = ExecutionState(
            task_id=f"e2e-test-2-{unique_id}",
            context_id=context_id,
            user_id="test-user",
            session_id=f"{agent_flow.flow_id}:{context_id}",
            content="где купить цветы",
        )
        result = await run_flow(container=agent_flow.container, flow=agent_flow, state=state)
        assert result.interrupt is not None, "Должен быть interrupt от субагента"
        assert "город" in result.interrupt.question.lower()
        assert "example_subflow" in result.nested_states, (
            f"Субагент должен быть в nested_states: {list(result.nested_states.keys())}"
        )
        assert len(result.interrupt_path) >= 2, (
            f"interrupt_path должен содержать [subagent, ask_user]: {result.interrupt_path}"
        )
        result.content = "москва"
        final_result = await run_flow(container=agent_flow.container, flow=agent_flow, state=result)
        assert final_result.interrupt is None, "После resume interrupt должен быть None"
        assert final_result.response is not None, "Должен быть response"
        subagent_state = final_result.nested_states.get("example_subflow")
        assert subagent_state is not None, "Субагент должен остаться в nested_states"
        assert len(subagent_state.messages) > 0, "Субагент должен иметь историю сообщений"

    @pytest.mark.asyncio
    async def test_multiple_interrupts_preserve_history(
        self, agent_flow, mock_llm_with_queue, unique_id
    ):
        """
        Множественные interrupts сохраняют историю.

        Сценарий:
        1. Субагент спрашивает город
        2. Resume с "москва"
        3. Субагент спрашивает район
        4. Resume с "раменки"
        5. Финальный ответ
        """
        mock_llm_with_queue(
            [
                {
                    "type": "tool_call",
                    "tool": "example_subflow",
                    "args": {"query": "найти магазин"},
                },
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Какой район?"}},
                "Магазин в Раменках, Москва.",
                "Рекомендую магазин в Раменках!",
            ]
        )
        context_id = f"e2e-context-3-{unique_id}"
        state = ExecutionState(
            task_id=f"e2e-test-3-{unique_id}",
            context_id=context_id,
            user_id="test-user",
            session_id=f"{agent_flow.flow_id}:{context_id}",
            content="найти цветочный магазин",
        )
        result1 = await run_flow(container=agent_flow.container, flow=agent_flow, state=state)
        assert result1.interrupt is not None
        assert "город" in result1.interrupt.question.lower()
        result1.content = "москва"
        result2 = await run_flow(container=agent_flow.container, flow=agent_flow, state=result1)
        assert result2.interrupt is not None
        assert "район" in result2.interrupt.question.lower()
        subagent_state = result2.nested_states.get("example_subflow")
        assert subagent_state is not None
        assert len(subagent_state.messages) >= 4, (
            f"Должно быть минимум 4 сообщения после первого resume: {len(subagent_state.messages)}"
        )
        result2.content = "раменки"
        result3 = await run_flow(container=agent_flow.container, flow=agent_flow, state=result2)
        assert result3.interrupt is None
        assert result3.response is not None
        final_subagent = result3.nested_states.get("example_subflow")
        assert final_subagent is not None
        assert len(final_subagent.messages) >= 6, (
            f"Должно быть минимум 6 сообщений: {len(final_subagent.messages)}"
        )

    @pytest.mark.asyncio
    async def test_interrupt_path_correctness(self, agent_flow, mock_llm_with_queue, unique_id):
        """
        Проверка правильности interrupt_path.

        При interrupt от субагента:
        - interrupt_path[0] = {type: "llm_node", id: "example_subflow"}
        - interrupt_path[1] = {type: "tool", id: "ask_user"}
        """
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "test"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "test?"}},
            ]
        )
        context_id = f"e2e-context-4-{unique_id}"
        state = ExecutionState(
            task_id=f"e2e-test-4-{unique_id}",
            context_id=context_id,
            user_id="test-user",
            session_id=f"{agent_flow.flow_id}:{context_id}",
            content="test",
        )
        result = await run_flow(container=agent_flow.container, flow=agent_flow, state=state)
        assert result.interrupt is not None
        assert len(result.interrupt_path) >= 2, (
            f"interrupt_path должен содержать минимум 2 элемента: {result.interrupt_path}"
        )
        first = result.interrupt_path[0]
        assert first.node_type == "llm_node", f"Первый элемент должен быть llm_node: {first}"
        assert first.node_id == "example_subflow", (
            f"ID должен быть example_subflow: {first.node_id}"
        )
        second = result.interrupt_path[1]
        assert second.node_type == "tool", f"Второй элемент должен быть tool: {second}"
        assert second.node_id == "ask_user", f"ID должен быть ask_user: {second.node_id}"

    @pytest.mark.asyncio
    async def test_nested_states_preserved_through_resume(
        self, agent_flow, mock_llm_with_queue, unique_id
    ):
        """
        nested_states сохраняются через весь цикл interrupt/resume.
        """
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "example_subflow", "args": {"query": "test"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Ваше имя?"}},
                "Привет, Тест!",
                "Ответ готов!",
            ]
        )
        context_id = f"e2e-context-5-{unique_id}"
        state = ExecutionState(
            task_id=f"e2e-test-5-{unique_id}",
            context_id=context_id,
            user_id="test-user",
            session_id=f"{agent_flow.flow_id}:{context_id}",
            content="тест",
        )
        result = await run_flow(container=agent_flow.container, flow=agent_flow, state=state)
        assert "example_subflow" in result.nested_states
        initial_messages_count = len(result.nested_states["example_subflow"].messages)
        result.content = "Тест"
        final_result = await run_flow(container=agent_flow.container, flow=agent_flow, state=result)
        assert "example_subflow" in final_result.nested_states
        final_messages_count = len(final_result.nested_states["example_subflow"].messages)
        assert final_messages_count > initial_messages_count, (
            f"Сообщений должно стать больше: {initial_messages_count} → {final_messages_count}"
        )


@pytest.mark.real_taskiq
class TestSubflowInterruptE2E:
    """
    E2E тесты interrupt в subflow (FlowNode) с реальным worker.

    Тестируют:
    1. Interrupt в CodeNode внутри subflow (FlowNode)
    2. Interrupt в LlmNode с ask_user внутри subflow
    3. Resume возвращает управление в правильную ноду субагента
    4. Ответ пользователя попадает именно в ту ноду которая его запросила
    """

    @pytest_asyncio.fixture
    async def child_agent_with_code_interrupt(self, app, container, unique_id):
        """
        Создает child агента с CodeNode, которая делает interrupt.

        Логика CodeNode:
        - Если content == "start" -> бросить interrupt с вопросом
        - Иначе -> использовать content как ответ и записать его в state
        """
        from apps.flows.src.models import FlowConfig

        flow_id = f"child_code_interrupt_{unique_id}"
        code_with_interrupt = '\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    content = state.get("content", "")\n\n    # Первый вызов - content == "start", нужно спросить имя\n    if content == "start":\n        raise FlowInterrupt(question="Как вас зовут?")\n\n    # Resume - content содержит ответ пользователя\n    user_name = content\n    state["received_answer"] = user_name  # Записываем полученный ответ для проверки\n    state["user_name"] = user_name\n    state["response"] = f"Привет, {user_name}! Ответ получен в CodeNode."\n    return {"response": state["response"], "user_name": user_name, "received_answer": user_name}\n'
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Child Agent with Code Interrupt",
            entry="ask_name_node",
            nodes={"ask_name_node": {"type": "code", "code": code_with_interrupt}},
            edges=[{"from_node": "ask_name_node", "to_node": None}],
        )
        await container.flow_repository.set(flow_config)
        yield flow_id
        await container.flow_repository.delete(flow_id)

    @pytest_asyncio.fixture
    async def parent_agent_with_subflow(
        self, app, container, unique_id, child_agent_with_code_interrupt
    ):
        """
        Создает parent агента с FlowNode (subflow), которая вызывает child агента.
        """
        from apps.flows.src.models import FlowConfig

        flow_id = f"parent_subflow_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Parent Agent with Subflow",
            entry="call_child",
            nodes={"call_child": {"type": "flow", "flow_id": child_agent_with_code_interrupt}},
            edges=[{"from_node": "call_child", "to_node": None}],
        )
        await container.flow_repository.set(flow_config)
        yield flow_id
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_subflow_code_node_interrupt(self, app, container, parent_agent_with_subflow):
        """
        Interrupt в CodeNode внутри subflow (FlowNode).

        Проверяем:
        1. CodeNode бросает FlowInterrupt
        2. Interrupt поднимается через FlowNode
        3. current_nodes указывает на subflow ноду для resume
        """
        flow = await container.flow_factory.get_flow(parent_agent_with_subflow)
        state = ExecutionState(
            task_id="subflow-code-test-1",
            context_id="subflow-context",
            user_id="test-user",
            session_id=f"{parent_agent_with_subflow}:subflow-context",
            content="start",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.interrupt is not None, "Должен быть interrupt от CodeNode"
        assert "зовут" in result.interrupt.question.lower(), (
            f"Вопрос должен содержать 'зовут': {result.interrupt.question}"
        )
        assert result.current_nodes == ["call_child"], (
            f"current_nodes должен указывать на subflow ноду: {result.current_nodes}"
        )

    @pytest.mark.asyncio
    async def test_subflow_code_node_resume_answer_reaches_node(
        self, app, container, parent_agent_with_subflow
    ):
        """
        ГЛАВНЫЙ ТЕСТ: Ответ пользователя попадает именно в CodeNode.

        Проверяем:
        1. Interrupt от CodeNode
        2. Resume с ответом "Иван"
        3. Ответ "Иван" попадает в CodeNode через state.content
        4. CodeNode записывает ответ в state.received_answer
        5. Response содержит имя, доказывая что ответ достиг CodeNode
        """
        flow = await container.flow_factory.get_flow(parent_agent_with_subflow)
        state = ExecutionState(
            task_id="subflow-code-test-2",
            context_id="subflow-context-2",
            user_id="test-user",
            session_id=f"{parent_agent_with_subflow}:subflow-context-2",
            content="start",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.interrupt is not None, "Должен быть interrupt"
        assert result.interrupt.question == "Как вас зовут?"
        result.content = "Иван"
        final_result = await run_flow(container=container, flow=flow, state=result)
        assert final_result.interrupt is None, "После resume interrupt должен быть None"
        assert final_result.response is not None, "Должен быть response"
        assert final_result.json_extra()["received_answer"] == "Иван"
        assert "иван" in final_result.response.lower(), (
            f"Response должен содержать 'Иван', получили: {final_result.response}"
        )
        assert "codenode" in final_result.response.lower(), (
            f"Response должен указывать что ответ обработан в CodeNode: {final_result.response}"
        )

    @pytest_asyncio.fixture
    async def child_agent_with_react_ask_user(self, app, container, unique_id):
        """
        Создает child агента с LlmNode и ask_user tool.

        child_agent:
            entry: "react_main" (LlmNode с ask_user tool)
        """
        from apps.flows.src.models import FlowConfig

        flow_id = f"child_react_ask_{unique_id}"
        ask_user_code = '\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    question = args.get("question", "")\n    raise FlowInterrupt(question=question)\n'
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Child Agent with React and ask_user",
            entry="react_main",
            nodes={
                "react_main": {
                    "type": "llm_node",
                    "prompt": "Ты агент который спрашивает имя пользователя. Используй ask_user для вопроса.",
                    "tools": [
                        {
                            "tool_id": "ask_user",
                            "description": "Задать вопрос пользователю",
                            "code": ask_user_code,
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "question": {"type": "string", "description": "Вопрос"}
                                },
                                "required": ["question"],
                            },
                        }
                    ],
                    "llm": {"model": "mock-gpt-4"},
                }
            },
            edges=[{"from_node": "react_main", "to_node": None}],
        )
        await container.flow_repository.set(flow_config)
        yield flow_id
        await container.flow_repository.delete(flow_id)

    @pytest_asyncio.fixture
    async def parent_agent_with_react_subflow(
        self, app, container, unique_id, child_agent_with_react_ask_user
    ):
        """
        Parent агент с LlmNode, который вызывает child агента как tool.
        """
        from apps.flows.src.models import FlowConfig

        flow_id = f"parent_react_subflow_{unique_id}"
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Parent Agent with React Subflow",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты главный агент. Для приветствия пользователя вызови child_agent.",
                    "tools": [
                        {
                            "tool_id": "child_agent",
                            "type": "llm_node",
                            "name": "Child Agent",
                            "description": "Агент для приветствия пользователей",
                            "parameters_schema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Запрос для дочернего агента",
                                    }
                                },
                                "required": ["query"],
                            },
                            "prompt": "Ты агент приветствия. Спроси имя используя ask_user.",
                            "tools": [
                                {
                                    "tool_id": "ask_user",
                                    "description": "Задать вопрос пользователю",
                                    "code": '\nfrom apps.flows.src.runtime.exceptions import FlowInterrupt\n\nasync def run(args, state):\n    question = args.get("question", "")\n    raise FlowInterrupt(question=question)\n',
                                    "parameters_schema": {
                                        "type": "object",
                                        "properties": {
                                            "question": {"type": "string", "description": "Вопрос"}
                                        },
                                        "required": ["question"],
                                    },
                                }
                            ],
                            "llm": {"model": "mock-gpt-4"},
                        }
                    ],
                    "llm": {"model": "mock-gpt-4"},
                }
            },
            edges=[{"from_node": "main", "to_node": None}],
        )
        await container.flow_repository.set(flow_config)
        yield flow_id
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_subflow_llm_node_ask_user_interrupt(
        self, app, container, parent_agent_with_react_subflow, mock_llm_with_queue
    ):
        """
        Interrupt от ask_user в LlmNode внутри subflow.

        Проверяем:
        1. Путь interrupt_path содержит [child_agent, ask_user]
        2. nested_states содержит состояние child_agent
        """
        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "child_agent", "args": {"query": "приветствие"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
            ]
        )
        flow = await container.flow_factory.get_flow(parent_agent_with_react_subflow)
        state = ExecutionState(
            task_id="subflow-react-test-1",
            context_id="subflow-react-context",
            user_id="test-user",
            session_id=f"{parent_agent_with_react_subflow}:subflow-react-context",
            content="Привет",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.interrupt is not None, "Должен быть interrupt от ask_user"
        assert "зовут" in result.interrupt.question.lower()
        assert len(result.interrupt_path) >= 2, (
            f"interrupt_path должен содержать [child_agent, ask_user]: {result.interrupt_path}"
        )
        first = result.interrupt_path[0]
        assert first.node_id == "child_agent", f"Первый элемент: {first.node_id}"
        second = result.interrupt_path[1]
        assert second.node_id == "ask_user", f"Второй элемент: {second.node_id}"
        assert "child_agent" in result.nested_states, (
            f"child_agent должен быть в nested_states: {list(result.nested_states.keys())}"
        )

    @pytest.mark.asyncio
    async def test_subflow_llm_node_resume_answer_in_messages(
        self, app, container, parent_agent_with_react_subflow, mock_llm_with_queue
    ):
        """
        ГЛАВНЫЙ ТЕСТ: Ответ пользователя появляется в messages child агента.

        Проверяем:
        1. После resume ответ "Иван" появляется в messages child_agent
        2. Ответ добавлен как tool result для ask_user
        3. LLM child получает ответ и формирует response с именем
        """
        from a2a.utils.message import get_message_text

        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "child_agent", "args": {"query": "приветствие"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
                "Привет, Иван! Ты написал свое имя и я его получил.",
                "Приветствие выполнено успешно!",
            ]
        )
        flow = await container.flow_factory.get_flow(parent_agent_with_react_subflow)
        state = ExecutionState(
            task_id="subflow-react-test-2",
            context_id="subflow-react-context-2",
            user_id="test-user",
            session_id=f"{parent_agent_with_react_subflow}:subflow-react-context-2",
            content="Привет",
        )
        result = await run_flow(container=container, flow=flow, state=state)
        assert result.interrupt is not None
        child_before = result.nested_states["child_agent"]
        messages_count_before = len(child_before.messages)
        result.content = "Иван"
        final_result = await run_flow(container=container, flow=flow, state=result)
        assert final_result.interrupt is None
        child_after = final_result.nested_states.get("child_agent")
        assert child_after is not None, "child_agent должен быть в nested_states"
        messages_count_after = len(child_after.messages)
        assert messages_count_after > messages_count_before, (
            f"После resume должно быть больше сообщений: {messages_count_before} -> {messages_count_after}"
        )
        found_answer = False
        for msg in child_after.messages:
            text = get_message_text(msg)
            if "Иван" in text or "иван" in text.lower():
                found_answer = True
                break
        assert found_answer, (
            f"Ответ 'Иван' должен быть в messages child_agent. Messages: {[get_message_text(m) for m in child_after.messages]}"
        )

    @pytest.mark.asyncio
    async def test_subflow_multiple_interrupts_answers_accumulate(
        self, app, container, parent_agent_with_react_subflow, mock_llm_with_queue
    ):
        """
        Несколько interrupt: каждый ответ появляется в истории child агента.

        Проверяем:
        1. После первого resume "Иван" появляется в messages
        2. После второго resume "Москва" тоже появляется в messages
        3. Оба ответа присутствуют в финальной истории child
        """
        from a2a.utils.message import get_message_text

        mock_llm_with_queue(
            [
                {"type": "tool_call", "tool": "child_agent", "args": {"query": "регистрация"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
                {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
                "Привет, Иван из Москвы! Оба ответа получены.",
                "Регистрация завершена.",
            ]
        )
        flow = await container.flow_factory.get_flow(parent_agent_with_react_subflow)
        state = ExecutionState(
            task_id="subflow-multi-interrupt",
            context_id="subflow-multi-context",
            user_id="test-user",
            session_id=f"{parent_agent_with_react_subflow}:subflow-multi-context",
            content="Регистрация",
        )
        result1 = await run_flow(container=container, flow=flow, state=state)
        assert result1.interrupt is not None
        result1.content = "Иван"
        result2 = await run_flow(container=container, flow=flow, state=result1)
        assert result2.interrupt is not None
        child_state_after_first = result2.nested_states.get("child_agent")
        assert child_state_after_first is not None
        messages_texts_1 = [get_message_text(m) for m in child_state_after_first.messages]
        found_ivan = any(("Иван" in t or "иван" in t.lower() for t in messages_texts_1))
        assert found_ivan, f"'Иван' должен быть в messages после первого resume: {messages_texts_1}"
        result2.content = "Москва"
        result3 = await run_flow(container=container, flow=flow, state=result2)
        assert result3.interrupt is None
        final_child = result3.nested_states.get("child_agent")
        assert final_child is not None
        messages_texts_final = [get_message_text(m) for m in final_child.messages]
        found_ivan_final = any(("Иван" in t or "иван" in t.lower() for t in messages_texts_final))
        found_moscow_final = any(
            ("Москва" in t or "москва" in t.lower() for t in messages_texts_final)
        )
        assert found_ivan_final, f"'Иван' должен быть в финальных messages: {messages_texts_final}"
        assert found_moscow_final, (
            f"'Москва' должен быть в финальных messages: {messages_texts_final}"
        )
