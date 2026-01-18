"""
E2E тесты для AgentInterrupt с реальным TaskIQ worker.

Тестируют:
1. Interrupt в простом tool (ask_user)
2. Interrupt в субагенте (react_node как tool)
3. Множественные interrupts с сохранением истории
4. Resume передает ответ в правильный субагент

БЕЗ МОКОВ - используют реальный LLM и TaskIQ worker.
"""

import pytest
import pytest_asyncio

from apps.agents.src.container import get_container
from core.state import ExecutionState


@pytest.mark.real_taskiq
class TestInterruptE2E:
    """E2E тесты interrupt с реальным worker."""

    @pytest_asyncio.fixture
    async def agent_flow(self, app):
        """Загружает example_react flow."""
        container = get_container()
        flow = await container.agent_factory.get_flow("example_react")
        return flow

    @pytest.mark.asyncio
    async def test_simple_ask_user_interrupt(self, agent_flow, mock_llm_with_queue):
        """
        Простой interrupt от ask_user tool.
        
        Сценарий:
        1. LLM вызывает ask_user
        2. Агент возвращает state с interrupt
        3. Resume с ответом пользователя
        4. LLM формирует финальный ответ
        """
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Как вас зовут?"}},
            "Приятно познакомиться, Иван!",
        ])
        
        state = ExecutionState(
            task_id="e2e-test-1",
            context_id="e2e-context",
            user_id="test-user",
            session_id="e2e-agent:e2e-context",
            content="Привет"
        )
        
        # Первый вызов - interrupt
        result = await agent_flow.run(state)
        
        assert result.interrupt is not None, "Должен быть interrupt"
        assert "зовут" in result.interrupt.question.lower()
        assert len(result.interrupt_path) > 0, "interrupt_path не должен быть пустым"
        
        # Resume с ответом
        result.content = "Иван"
        final_result = await agent_flow.run(result)
        
        assert final_result.interrupt is None, "После resume interrupt должен быть None"
        assert final_result.response is not None, "Должен быть response"
        assert "иван" in final_result.response.lower()

    @pytest.mark.asyncio
    async def test_subagent_interrupt_and_resume(self, agent_flow, mock_llm_with_queue):
        """
        Interrupt в субагенте (react_node как tool).
        
        Сценарий:
        1. Главный агент вызывает example_subagent
        2. Субагент вызывает ask_user
        3. State сохраняется в nested_states
        4. Resume передает ответ в субагента
        5. Субагент отвечает
        6. Главный агент формирует финальный ответ
        """
        mock_llm_with_queue([
            # Главный агент вызывает субагента
            {"type": "tool_call", "tool": "example_subagent", "args": {"query": "найти магазин"}},
            # Субагент спрашивает город
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
            # После resume - субагент отвечает
            "Магазин на Тверской, Москва.",
            # Главный агент формирует ответ
            "Рекомендую магазин на Тверской!",
        ])
        
        state = ExecutionState(
            task_id="e2e-test-2",
            context_id="e2e-context",
            user_id="test-user",
            session_id="e2e-agent:e2e-context",
            content="где купить цветы"
        )
        
        # Первый вызов - interrupt от субагента
        result = await agent_flow.run(state)
        
        assert result.interrupt is not None, "Должен быть interrupt от субагента"
        assert "город" in result.interrupt.question.lower()
        
        # Проверяем что nested_states содержит субагента
        assert "example_subagent" in result.nested_states, \
            f"Субагент должен быть в nested_states: {list(result.nested_states.keys())}"
        
        # Проверяем interrupt_path
        assert len(result.interrupt_path) >= 2, \
            f"interrupt_path должен содержать [subagent, ask_user]: {result.interrupt_path}"
        
        # Resume с ответом
        result.content = "москва"
        final_result = await agent_flow.run(result)
        
        assert final_result.interrupt is None, "После resume interrupt должен быть None"
        assert final_result.response is not None, "Должен быть response"
        
        # Проверяем историю субагента
        subagent_state = final_result.nested_states.get("example_subagent")
        assert subagent_state is not None, "Субагент должен остаться в nested_states"
        assert len(subagent_state.messages) > 0, "Субагент должен иметь историю сообщений"

    @pytest.mark.asyncio
    async def test_multiple_interrupts_preserve_history(self, agent_flow, mock_llm_with_queue):
        """
        Множественные interrupts сохраняют историю.
        
        Сценарий:
        1. Субагент спрашивает город
        2. Resume с "москва"
        3. Субагент спрашивает район
        4. Resume с "раменки"
        5. Финальный ответ
        """
        mock_llm_with_queue([
            # Главный → субагент
            {"type": "tool_call", "tool": "example_subagent", "args": {"query": "найти магазин"}},
            # Субагент: город?
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "В каком городе?"}},
            # После "москва": район?
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Какой район?"}},
            # После "раменки": ответ
            "Магазин в Раменках, Москва.",
            # Главный: финал
            "Рекомендую магазин в Раменках!",
        ])
        
        state = ExecutionState(
            task_id="e2e-test-3",
            context_id="e2e-context",
            user_id="test-user",
            session_id="e2e-agent:e2e-context",
            content="найти цветочный магазин"
        )
        
        # 1. Первый interrupt (город)
        result1 = await agent_flow.run(state)
        assert result1.interrupt is not None
        assert "город" in result1.interrupt.question.lower()
        
        # 2. Resume "москва" → второй interrupt (район)
        result1.content = "москва"
        result2 = await agent_flow.run(result1)
        assert result2.interrupt is not None
        assert "район" in result2.interrupt.question.lower()
        
        # Проверяем что история накопилась
        subagent_state = result2.nested_states.get("example_subagent")
        assert subagent_state is not None
        # После первого resume должно быть 4 messages: user, assistant, tool(москва), assistant
        assert len(subagent_state.messages) >= 4, \
            f"Должно быть минимум 4 сообщения после первого resume: {len(subagent_state.messages)}"
        
        # 3. Resume "раменки" → финальный ответ
        result2.content = "раменки"
        result3 = await agent_flow.run(result2)
        
        assert result3.interrupt is None
        assert result3.response is not None
        
        # Проверяем финальную историю
        final_subagent = result3.nested_states.get("example_subagent")
        assert final_subagent is not None
        # После второго resume: +2 messages (tool(раменки), assistant)
        assert len(final_subagent.messages) >= 6, \
            f"Должно быть минимум 6 сообщений: {len(final_subagent.messages)}"

    @pytest.mark.asyncio
    async def test_interrupt_path_correctness(self, agent_flow, mock_llm_with_queue):
        """
        Проверка правильности interrupt_path.
        
        При interrupt от субагента:
        - interrupt_path[0] = {type: "react_node", id: "example_subagent"}
        - interrupt_path[1] = {type: "tool", id: "ask_user"}
        """
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "example_subagent", "args": {"query": "test"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "test?"}},
        ])
        
        state = ExecutionState(
            task_id="e2e-test-4",
            context_id="e2e-context",
            user_id="test-user",
            session_id="e2e-agent:e2e-context",
            content="test"
        )
        
        result = await agent_flow.run(state)
        
        assert result.interrupt is not None
        assert len(result.interrupt_path) >= 2, \
            f"interrupt_path должен содержать минимум 2 элемента: {result.interrupt_path}"
        
        # Первый элемент - субагент
        first = result.interrupt_path[0]
        assert first.type == "react_node", f"Первый элемент должен быть react_node: {first}"
        assert first.id == "example_subagent", f"ID должен быть example_subagent: {first.id}"
        
        # Второй элемент - ask_user
        second = result.interrupt_path[1]
        assert second.type == "tool", f"Второй элемент должен быть tool: {second}"
        assert second.id == "ask_user", f"ID должен быть ask_user: {second.id}"

    @pytest.mark.asyncio
    async def test_nested_states_preserved_through_resume(self, agent_flow, mock_llm_with_queue):
        """
        nested_states сохраняются через весь цикл interrupt/resume.
        """
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "example_subagent", "args": {"query": "test"}},
            {"type": "tool_call", "tool": "ask_user", "args": {"question": "Ваше имя?"}},
            "Привет, Тест!",
            "Ответ готов!",
        ])
        
        state = ExecutionState(
            task_id="e2e-test-5",
            context_id="e2e-context",
            user_id="test-user",
            session_id="e2e-agent:e2e-context",
            content="тест"
        )
        
        # Interrupt
        result = await agent_flow.run(state)
        assert "example_subagent" in result.nested_states
        
        initial_messages_count = len(result.nested_states["example_subagent"].messages)
        
        # Resume
        result.content = "Тест"
        final_result = await agent_flow.run(result)
        
        assert "example_subagent" in final_result.nested_states
        final_messages_count = len(final_result.nested_states["example_subagent"].messages)
        
        # После resume должно быть больше сообщений
        assert final_messages_count > initial_messages_count, \
            f"Сообщений должно стать больше: {initial_messages_count} → {final_messages_count}"
