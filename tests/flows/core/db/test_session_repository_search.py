"""
Тесты для StateRepository.search_sessions().

Используют реальную БД без моков.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

import pytest

from apps.flows.src.container import get_container
from apps.flows.src.state import create_initial_state


def create_test_state(
    session_id: str,
    user_id: str,
    flow_id: str,
    first_message: str = None,
    message_count: int = 0,
) -> Dict[str, Any]:
    """
    Создает тестовый state для сессии.

    Args:
        session_id: ID сессии (формат 'flow_id:context_id')
        user_id: ID пользователя
        flow_id: ID flow
        first_message: Первое сообщение пользователя
        message_count: Количество сообщений
    """
    import uuid
    task_id = str(uuid.uuid4())
    context_id = str(uuid.uuid4())
    state = create_initial_state(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
    )

    # Добавляем сообщения
    from a2a.types import Message, Part, Role, TextPart
    messages = []
    if first_message:
        messages.append(Message(
            messageId="msg1",
            role=Role.user,
            parts=[Part(root=TextPart(text=first_message))],
            taskId=task_id,
        ))

    # Добавляем дополнительные сообщения для message_count
    for i in range(max(0, message_count - (1 if first_message else 0))):
        role = Role.agent if i % 2 == 0 else Role.user
        messages.append(Message(
            messageId=f"msg{i+2}",
            role=role,
            parts=[Part(root=TextPart(text=f"Message {i+2}"))],
            taskId=task_id,
        ))

    state.messages = messages

    return state.model_dump(exclude_none=False)


class TestStateRepositorySearchSessions:
    """Тесты метода search_sessions() в StateRepository."""

    @pytest.mark.asyncio
    async def test_search_all_sessions(self, app, unique_id):
        """Поиск всех сессий без фильтров."""
        container = get_container()
        repo = container.state_repository

        session1_id = f"flow1_{unique_id}:session1_{unique_id}"
        session2_id = f"flow2_{unique_id}:session2_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=f"user1_{unique_id}",
            flow_id=f"flow1_{unique_id}",
            first_message="Hello",
            message_count=5,
        )

        state2 = create_test_state(
            session_id=session2_id,
            user_id=f"user2_{unique_id}",
            flow_id=f"flow2_{unique_id}",
            first_message="Hi",
            message_count=10,
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)

        sessions, total = await repo.search_sessions(limit=500)

        assert total >= 2
        session_ids = [s.session_id for s in sessions]
        assert session1_id in session_ids
        assert session2_id in session_ids

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_search_by_user_id(self, app, unique_id):
        """Поиск сессий по user_id."""
        container = get_container()
        repo = container.state_repository

        target_user = f"target_user_{unique_id}"
        other_user = f"other_user_{unique_id}"

        session1_id = f"flow1_{unique_id}:session1_{unique_id}"
        session2_id = f"flow2_{unique_id}:session2_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=target_user,
            flow_id=f"flow1_{unique_id}",
        )

        state2 = create_test_state(
            session_id=session2_id,
            user_id=other_user,
            flow_id=f"flow2_{unique_id}",
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)

        sessions, total = await repo.search_sessions(user_id=target_user, limit=100)

        assert total == 1
        assert sessions[0].session_id == session1_id
        assert sessions[0].user_id == target_user

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_search_by_agent_id(self, app, unique_id):
        """Поиск сессий по flow_id."""
        container = get_container()
        repo = container.state_repository

        target_flow = f"target_flow_{unique_id}"
        other_flow = f"other_flow_{unique_id}"

        session1_id = f"{target_flow}:session1_{unique_id}"
        session2_id = f"{other_flow}:session2_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=f"user1_{unique_id}",
            flow_id=target_flow,
        )

        state2 = create_test_state(
            session_id=session2_id,
            user_id=f"user2_{unique_id}",
            flow_id=other_flow,
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)

        sessions, total = await repo.search_sessions(flow_id=target_flow, limit=100)

        assert total == 1
        assert sessions[0].session_id == session1_id
        assert sessions[0].flow_id == target_flow

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_search_by_date_range(self, app, unique_id):
        """Поиск сессий по диапазону дат."""
        container = get_container()
        repo = container.state_repository

        base_user = f"date_test_user_{unique_id}"
        now = datetime.now(timezone.utc)
        date_from = now - timedelta(days=2)
        date_to = now - timedelta(days=1)
        date_old = now - timedelta(days=3)
        date_in_range = date_from + timedelta(hours=12)
        date_new = now

        session_old_id = f"flow1_{unique_id}:session_old_{unique_id}"
        session_in_range_id = f"flow2_{unique_id}:session_in_range_{unique_id}"
        session_new_id = f"flow3_{unique_id}:session_new_{unique_id}"

        state_old = create_test_state(
            session_id=session_old_id,
            user_id=base_user,
            flow_id=f"flow1_{unique_id}",
        )

        state_in_range = create_test_state(
            session_id=session_in_range_id,
            user_id=base_user,
            flow_id=f"flow2_{unique_id}",
        )

        state_new = create_test_state(
            session_id=session_new_id,
            user_id=base_user,
            flow_id=f"flow3_{unique_id}",
        )

        await repo.set(session_old_id, state_old)
        await repo.set(session_in_range_id, state_in_range)
        await repo.set(session_new_id, state_new)

        # Устанавливаем created_at через SQLAlchemy
        from sqlalchemy import update

        from apps.flows.src.db.models import States

        key_old = repo._build_final_key(repo._get_key(session_old_id))
        key_in_range = repo._build_final_key(repo._get_key(session_in_range_id))
        key_new = repo._build_final_key(repo._get_key(session_new_id))

        async with repo._storage._get_session() as session:
            await session.execute(
                update(States)
                .where(States.key == key_old)
                .values(created_at=date_old.replace(tzinfo=None), updated_at=date_old.replace(tzinfo=None))
            )
            await session.execute(
                update(States)
                .where(States.key == key_in_range)
                .values(created_at=date_in_range.replace(tzinfo=None), updated_at=date_in_range.replace(tzinfo=None))
            )
            await session.execute(
                update(States)
                .where(States.key == key_new)
                .values(created_at=date_new.replace(tzinfo=None), updated_at=date_new.replace(tzinfo=None))
            )
            await session.commit()

        sessions, total = await repo.search_sessions(
            user_id=base_user,
            date_from=date_from.replace(tzinfo=None),
            date_to=date_to.replace(tzinfo=None),
            limit=100,
        )

        assert total == 1
        assert sessions[0].session_id == session_in_range_id

        await repo.delete(session_old_id)
        await repo.delete(session_in_range_id)
        await repo.delete(session_new_id)

    @pytest.mark.asyncio
    async def test_search_combined_filters(self, app, unique_id):
        """Поиск с комбинацией фильтров."""
        container = get_container()
        repo = container.state_repository

        target_user = f"target_user_{unique_id}"
        target_flow = f"target_flow_{unique_id}"
        datetime.now(timezone.utc)

        session1_id = f"{target_flow}:session1_{unique_id}"
        session2_id = f"other_flow_{unique_id}:session2_{unique_id}"
        session3_id = f"{target_flow}:session3_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=target_user,
            flow_id=target_flow,
        )

        state2 = create_test_state(
            session_id=session2_id,
            user_id=target_user,
            flow_id=f"other_flow_{unique_id}",
        )

        state3 = create_test_state(
            session_id=session3_id,
            user_id=f"other_user_{unique_id}",
            flow_id=target_flow,
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)
        await repo.set(session3_id, state3)

        sessions, total = await repo.search_sessions(
            user_id=target_user,
            flow_id=target_flow,
            limit=100,
        )

        assert total == 1
        assert sessions[0].session_id == session1_id
        assert sessions[0].user_id == target_user
        assert sessions[0].flow_id == target_flow

        await repo.delete(session1_id)
        await repo.delete(session2_id)
        await repo.delete(session3_id)

    @pytest.mark.asyncio
    async def test_search_pagination(self, app, unique_id):
        """Проверка пагинации в search()."""
        container = get_container()
        repo = container.state_repository

        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"
        sessions_to_create = 5

        for i in range(sessions_to_create):
            session_id = f"{flow_id}:session_{i}_{unique_id}"
            state = create_test_state(
                session_id=session_id,
                user_id=base_user,
                flow_id=flow_id,
            )
            await repo.set(session_id, state)

        page1, total1 = await repo.search_sessions(user_id=base_user, limit=2, offset=0)
        page2, total2 = await repo.search_sessions(user_id=base_user, limit=2, offset=2)

        assert total1 == total2 == sessions_to_create
        assert len(page1) == 2
        assert len(page2) == 2

        page1_ids = {s.session_id for s in page1}
        page2_ids = {s.session_id for s in page2}
        assert page1_ids.isdisjoint(page2_ids)

        for i in range(sessions_to_create):
            await repo.delete(f"{flow_id}:session_{i}_{unique_id}")

    @pytest.mark.asyncio
    async def test_search_empty_result(self, app, unique_id):
        """Поиск с фильтрами, которые не дают результатов."""
        container = get_container()
        repo = container.state_repository

        sessions, total = await repo.search_sessions(
            user_id=f"nonexistent_user_{unique_id}",
            limit=100,
        )

        assert total == 0
        assert len(sessions) == 0

    @pytest.mark.asyncio
    async def test_search_ordering(self, app, unique_id):
        """Проверка сортировки по дате создания (DESC)."""
        container = get_container()
        repo = container.state_repository

        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"
        now = datetime.now(timezone.utc)

        session1_id = f"{flow_id}:session1_{unique_id}"
        session2_id = f"{flow_id}:session2_{unique_id}"
        session3_id = f"{flow_id}:session3_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=base_user,
            flow_id=flow_id,
        )

        state2 = create_test_state(
            session_id=session2_id,
            user_id=base_user,
            flow_id=flow_id,
        )

        state3 = create_test_state(
            session_id=session3_id,
            user_id=base_user,
            flow_id=flow_id,
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)
        await repo.set(session3_id, state3)

        # Устанавливаем created_at через SQLAlchemy для проверки сортировки
        from sqlalchemy import update

        from apps.flows.src.db.models import States

        key1 = repo._build_final_key(repo._get_key(session1_id))
        key2 = repo._build_final_key(repo._get_key(session2_id))
        key3 = repo._build_final_key(repo._get_key(session3_id))

        async with repo._storage._get_session() as session:
            date1 = (now - timedelta(hours=2)).replace(tzinfo=None)
            date2 = (now - timedelta(hours=1)).replace(tzinfo=None)
            date3 = now.replace(tzinfo=None)
            await session.execute(
                update(States)
                .where(States.key == key1)
                .values(created_at=date1, updated_at=date1)
            )
            await session.execute(
                update(States)
                .where(States.key == key2)
                .values(created_at=date2, updated_at=date2)
            )
            await session.execute(
                update(States)
                .where(States.key == key3)
                .values(created_at=date3, updated_at=date3)
            )
            await session.commit()

        sessions, total = await repo.search_sessions(user_id=base_user, limit=100)

        assert total == 3
        assert sessions[0].session_id == session3_id
        assert sessions[1].session_id == session2_id
        assert sessions[2].session_id == session1_id

        await repo.delete(session1_id)
        await repo.delete(session2_id)
        await repo.delete(session3_id)

