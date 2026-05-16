"""
Тесты для reason tool.

Без моков - реальный tool.
"""

import pytest

from apps.flows.tools.agent_session_tools import reason
from core.state import ExecutionState


class TestReasonTool:
    """Тесты reason tool."""

    @pytest.mark.asyncio
    async def test_reason_saves_to_state(self):
        """Рассуждения сохраняются в state.reasoning_history."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        result = await reason.run(
            args={
                "observation": "Пользователь спрашивает про склад",
                "analysis": "Нужно узнать название склада",
                "plan": "Спросить название у пользователя",
                "next_action": "Вызову ask_user",
            },
            state=state,
        )

        assert len(state.reasoning_history) == 1

        entry = state.reasoning_history[0]
        assert entry["observation"] == "Пользователь спрашивает про склад"
        assert entry["analysis"] == "Нужно узнать название склада"
        assert entry["plan"] == "Спросить название у пользователя"
        assert entry["next_action"] == "Вызову ask_user"

        assert "Рассуждения записаны" in result
        assert "ask_user" in result

    @pytest.mark.asyncio
    async def test_reason_sets_pending_flag(self):
        """reason устанавливает pending_reasoning."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        await reason.run(
            args={
                "observation": "Тест",
                "analysis": "Анализ",
                "plan": "План",
                "next_action": "Действие",
            },
            state=state,
        )

        assert state.pending_reasoning is not None
        assert state.pending_reasoning["observation"] == "Тест"

    @pytest.mark.asyncio
    async def test_multiple_reasoning_calls_accumulate(self):
        """Несколько вызовов накапливаются в истории."""
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        await reason.run(
            args={
                "observation": "Первое наблюдение",
                "analysis": "Первый анализ",
                "plan": "Первый план",
                "next_action": "Первое действие",
            },
            state=state,
        )

        await reason.run(
            args={
                "observation": "Второе наблюдение",
                "analysis": "Второй анализ",
                "plan": "Второй план",
                "next_action": "Второе действие",
            },
            state=state,
        )

        assert len(state.reasoning_history) == 2
        assert state.reasoning_history[0]["observation"] == "Первое наблюдение"
        assert state.reasoning_history[1]["observation"] == "Второе наблюдение"

    def test_tool_has_correct_name(self):
        """Tool имеет имя 'reason'."""
        assert reason.name == "reason"

    def test_tool_has_correct_type(self):
        """Tool имеет react_role REASON."""
        from apps.flows.src.models.enums import ReactToolRole
        assert reason.react_role == ReactToolRole.REASON

    def test_tool_has_tags(self):
        """Tool имеет теги reasoning и internal."""
        assert "reasoning" in reason.tags
        assert "internal" in reason.tags

    def test_tool_parameters_generated(self):
        """Parameters генерируются из функции."""
        params = reason.parameters

        assert "properties" in params
        assert "observation" in params["properties"]
        assert "analysis" in params["properties"]
        assert "plan" in params["properties"]
        assert "next_action" in params["properties"]
