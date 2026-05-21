"""
Тесты для StateManager.
State содержит A2A типы (Message).
"""

import uuid

import pytest
from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.container import get_container
from apps.flows.src.state import StateManager
from core.state import ExecutionState


def _msg(text: str, role: Role = Role.user) -> Message:
    """Создаёт A2A Message для тестов."""
    return Message(
        messageId=str(uuid.uuid4()),
        role=role,
        parts=[Part(root=TextPart(text=text))],
    )


class TestStateManager:
    """Тесты StateManager."""

    @pytest.fixture
    def state_manager(self, app) -> StateManager:
        """Production StateManager с реальными Redis и БД."""
        container = get_container()
        return container.state_manager

    @pytest.mark.asyncio
    async def test_get_state_returns_none_for_new_session(self, state_manager: StateManager):
        """get_state возвращает None для новой сессии."""
        state = await state_manager.get_state("new_session_123")

        assert state is None

    @pytest.mark.asyncio
    async def test_save_and_get_state(self, state_manager: StateManager):
        """Сохранение и получение state с A2A Message."""
        from core.state import ExecutionState

        session_id = f"test_save_get_state_{uuid.uuid4().hex[:8]}"

        user_msg = _msg("Hello", Role.user)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[user_msg],
            variables={"key": "value"},
            custom_field=123
        )

        await state_manager.save_state(session_id, state)
        loaded = await state_manager.get_state(session_id)

        # messages содержат A2A Message объекты
        assert len(loaded.messages) == 1
        assert isinstance(loaded.messages[0], Message)
        assert loaded.messages[0].role == Role.user
        assert loaded.messages[0].parts[0].root.text == "Hello"

        assert loaded.variables == {"key": "value"}
        assert loaded.custom_field == 123

        # Cleanup
        await state_manager.delete_state(session_id)

    @pytest.mark.asyncio
    async def test_delete_state(self, state_manager: StateManager):
        """Удаление state."""
        from core.state import ExecutionState

        session_id = f"test_delete_state_{uuid.uuid4().hex[:8]}"

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            data="test"
        )
        await state_manager.save_state(session_id, state)
        await state_manager.delete_state(session_id)

        # После удаления должен быть None
        state = await state_manager.get_state(session_id)
        assert state is None

    def test_add_message(self, state_manager: StateManager):
        """Добавление A2A Message в state."""
        from core.state import ExecutionState

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        msg1 = _msg("Hello!", Role.user)
        msg2 = _msg("Hi there!", Role.agent)
        state_manager.add_message(state, msg1)
        state_manager.add_message(state, msg2)

        assert len(state.messages) == 2
        assert state.messages[0].role == Role.user
        assert state.messages[0].parts[0].root.text == "Hello!"
        assert state.messages[1].role == Role.agent
        assert state.messages[1].parts[0].root.text == "Hi there!"

    def test_add_user_message(self, state_manager: StateManager):
        """add_user_message создаёт Message с role=user."""
        from core.state import ExecutionState

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        state_manager.add_user_message(state, "User message")

        assert len(state.messages) == 1
        assert state.messages[0].role == Role.user
        assert state.messages[0].parts[0].root.text == "User message"

    def test_add_agent_message(self, state_manager: StateManager):
        """add_agent_message создаёт Message с role=agent."""
        from core.state import ExecutionState

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        state_manager.add_agent_message(state, "Agent response")

        assert len(state.messages) == 1
        assert state.messages[0].role == Role.agent
        assert state.messages[0].parts[0].root.text == "Agent response"

    def test_add_message_creates_messages_list(self, state_manager: StateManager):
        """add_message создаёт messages если его нет."""
        from core.state import ExecutionState

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        state_manager.add_user_message(state, "Test")

        assert len(state.messages) == 1

    @pytest.mark.asyncio
    async def test_get_messages(self, state_manager: StateManager):
        """Получение списка A2A Message."""
        from core.state import ExecutionState

        msg1 = _msg("Hello", Role.user)
        msg2 = _msg("Hi", Role.agent)
        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context",
            messages=[msg1, msg2]
        )

        messages = await state_manager.get_messages(state)

        assert len(messages) == 2
        assert messages[0].role == Role.user
        assert messages[1].role == Role.agent

    @pytest.mark.asyncio
    async def test_get_messages_empty(self, state_manager: StateManager):
        """get_messages для пустого state."""
        from core.state import ExecutionState

        state = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )

        messages = await state_manager.get_messages(state)

        assert messages == []

    @pytest.mark.asyncio
    async def test_state_persistence(self, state_manager: StateManager):
        """State сохраняется между вызовами."""
        from core.state import ExecutionState

        session_id = f"test_persistence_{uuid.uuid4().hex[:8]}"

        # Первый вызов - создаём state
        state1 = ExecutionState(
            task_id="test-task",
            context_id="test-context",
            user_id="test-user",
            session_id="test-agent:test-context"
        )
        state_manager.add_user_message(state1, "Message 1")
        await state_manager.save_state(session_id, state1)

        # Второй вызов - загружаем и добавляем
        state2 = await state_manager.get_state(session_id)
        state_manager.add_user_message(state2, "Message 2")
        await state_manager.save_state(session_id, state2)

        # Проверяем
        final_state = await state_manager.get_state(session_id)
        assert len(final_state.messages) == 2
        assert final_state.messages[0].parts[0].root.text == "Message 1"
        assert final_state.messages[1].parts[0].root.text == "Message 2"

        # Cleanup
        await state_manager.delete_state(session_id)


class TestRedisBackedStateManager:
    """Проверки production lifecycle: real Redis для hot state, real DB для terminal."""

    @pytest.mark.asyncio
    async def test_intermediate_state_is_stored_in_real_redis_only(self, app):
        container = get_container()
        manager = container.state_manager
        repo = container.state_repository
        session_id = f"redis_hot_flow:{uuid.uuid4().hex}"
        state = ExecutionState(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="draft",
        )

        try:
            await manager.save_state(session_id, state)

            assert await repo.get(session_id) is None
            assert await container.redis_client.get(manager._state_key(session_id)) is not None

            loaded = await manager.get_state(session_id)
            assert loaded is not None
            assert loaded.content == "draft"
            assert (
                await manager.resolve_session_id_by_flow_and_identifier(
                    "redis_hot_flow", state.task_id
                )
                == session_id
            )
            assert (
                await manager.resolve_session_id_by_flow_and_identifier(
                    "redis_hot_flow", state.context_id
                )
                == session_id
            )
        finally:
            await manager.delete_state(session_id)

    @pytest.mark.asyncio
    async def test_terminal_state_is_stored_in_db_and_clears_real_redis(self, app):
        container = get_container()
        manager = container.state_manager
        repo = container.state_repository
        session_id = f"redis_terminal_flow:{uuid.uuid4().hex}"
        state = ExecutionState(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            response="done",
        )

        try:
            await manager.save_state(session_id, state)
            task_key, context_key = manager._index_keys(state)

            await manager.save_terminal_state(session_id, state, "completed")

            assert await container.redis_client.get(manager._state_key(session_id)) is None
            assert await container.redis_client.get(task_key) is None
            assert await container.redis_client.get(context_key) is None

            persisted = await repo.get(session_id)
            assert persisted is not None
            assert persisted.terminal_status == "completed"

            loaded = await manager.get_state(session_id)
            assert loaded is not None
            assert loaded.terminal_status == "completed"
            assert loaded.response == "done"
        finally:
            await manager.delete_state(session_id)

    @pytest.mark.asyncio
    async def test_db_fallback_ignores_non_terminal_snapshot_when_real_redis_is_empty(self, app):
        container = get_container()
        manager = container.state_manager
        repo = container.state_repository
        session_id = f"redis_stale_db_flow:{uuid.uuid4().hex}"
        state = ExecutionState(
            task_id=f"task-{uuid.uuid4().hex}",
            context_id=session_id.split(":", 1)[1],
            user_id="test-user",
            session_id=session_id,
            content="old-db-checkpoint",
        )

        try:
            await repo.set(session_id, state)

            assert await container.redis_client.get(manager._state_key(session_id)) is None
            assert await manager.get_state(session_id) is None
        finally:
            await manager.delete_state(session_id)
