"""
Тесты репозиториев (PostgreSQL).

Используют реальную БД через app fixture.
"""

import pytest
from typing import Any, Dict

from apps.agents.src.container import get_container
from core.db.repositories import Variable
from apps.agents.src.models import (
    NodeConfig,
    AgentConfig,
    ToolReference,
    CodeMode,
    SessionConfig,
)
from core.state import ExecutionState


class TestNodeRepository:
    """Тесты NodeRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_node(self, app):
        """Сохранение и получение ноды."""
        container = get_container()
        repo = container.node_repository

        node = NodeConfig(
            node_id="test_node_repo",
            type="react_node",
            name="Test Node",
            description="For testing",
            prompt="Test prompt",
        )

        await repo.set(node)
        loaded = await repo.get("test_node_repo")

        assert loaded is not None
        assert loaded.node_id == "test_node_repo"
        assert loaded.name == "Test Node"

        # Cleanup
        await repo.delete("test_node_repo")

    @pytest.mark.asyncio
    async def test_get_nonexistent_node(self, app):
        """Получение несуществующей ноды возвращает None."""
        container = get_container()
        repo = container.node_repository

        result = await repo.get("nonexistent_node_xyz")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_node(self, app):
        """Удаление ноды."""
        container = get_container()
        repo = container.node_repository

        node = NodeConfig(
            node_id="node_to_delete",
            type="react_node",
            name="Delete Me",
        )
        await repo.set(node)
        await repo.delete("node_to_delete")

        result = await repo.get("node_to_delete")
        assert result is None


class TestAgentRepository:
    """Тесты AgentRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_flow(self, app):
        """Сохранение и получение flow."""
        container = get_container()
        repo = container.agent_repository

        flow = AgentConfig(
            agent_id="test_flow_repo",
            name="Test Agent",
            description="For testing",
            entry="main",
            nodes={
                "main": {
                    "type": "react_node",
                    "prompt": "Test",
                    "next": None
                }
            },
        )

        await repo.set(flow)
        loaded = await repo.get("test_flow_repo")

        assert loaded is not None
        assert loaded.agent_id == "test_flow_repo"
        assert "main" in loaded.nodes

        await repo.delete("test_flow_repo")

    @pytest.mark.asyncio
    async def test_list_all_flows(self, app):
        """Получение списка всех flows."""
        container = get_container()
        repo = container.agent_repository

        flows = await repo.list_all()
        assert isinstance(flows, list)


class TestToolRepository:
    """Тесты ToolRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_tool(self, app):
        """Сохранение и получение tool."""
        container = get_container()
        repo = container.tool_repository

        tool = ToolReference(
            tool_id="test_tool_repo",
            title="Test Tool",
            description="For testing",
            type="function",
            code_mode=CodeMode.INLINE_CODE,
            code="def execute(args, state):\n    return args.get('x', 0) + 1",
        )

        await repo.set(tool)
        loaded = await repo.get("test_tool_repo")

        assert loaded is not None
        assert loaded.tool_id == "test_tool_repo"

        await repo.delete("test_tool_repo")


class TestVariableRepository:
    """Тесты VariableRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_variable(self, app):
        """Сохранение и получение переменной."""
        container = get_container()
        repo = container.variable_repository

        var = Variable(
            key="test_var",
            value="test_value",
            description="Test variable",
        )

        await repo.set(var)
        loaded = await repo.get("test_var")

        assert loaded is not None
        assert loaded.key == "test_var"
        assert loaded.value == "test_value"

        await repo.delete("test_var")

    @pytest.mark.asyncio
    async def test_get_all_variables(self, app):
        """Получение всех переменных."""
        container = get_container()
        repo = container.variable_repository

        # Создаём несколько переменных
        await repo.set(Variable(key="var1", value="value1"))
        await repo.set(Variable(key="var2", value="value2"))

        all_vars = await repo.get_all_variables()

        assert "var1" in all_vars
        assert "var2" in all_vars

        # Cleanup
        await repo.delete("var1")
        await repo.delete("var2")


class TestSessionRepository:
    """Тесты SessionRepository - удален, используйте StateRepository.search_sessions()"""

    @pytest.mark.asyncio
    async def test_set_and_get_session(self, app):
        """SessionRepository удален, используйте StateRepository.search_sessions()"""
        pytest.skip("SessionRepository удален, используйте StateRepository.search_sessions()")


class TestStateRepository:
    """Тесты StateRepository."""

    @pytest.mark.asyncio
    async def test_set_and_get_state(self, app):
        """Сохранение и получение state."""
        container = get_container()
        repo = container.state_repository

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            content="test",
            messages=[],
            node="main"
        )
        from a2a.types import Message, Part, Role, TextPart
        message = Message(
            messageId="test-msg",
            role=Role.user,
            parts=[Part(root=TextPart(text="Hello"))],
            taskId="test-task"
        )
        state.messages.append(message)

        await repo.set("test_state_session", state.model_dump())
        loaded = await repo.get("test_state_session")

        assert loaded is not None
        assert loaded["content"] == "test"
        assert len(loaded.get("messages", [])) == 1

        await repo.delete("test_state_session")

