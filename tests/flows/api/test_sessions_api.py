"""
Тесты для Sessions API endpoints.

Используют реальную БД и HTTP клиент без моков.
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
    branch_id: str = "default",
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
        branch_id=branch_id,
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

    return state.model_dump()


class TestSessionsAPI:
    """Тесты /api/v1/sessions"""

    @pytest.mark.asyncio
    async def test_list_sessions(self, client, app, unique_id):
        """GET /api/v1/sessions возвращает список сессий."""
        container = get_container()
        repo = container.state_repository

        flow_id = f"flow_{unique_id}"
        user_id = f"user_{unique_id}"
        session_id = f"{flow_id}:context_{unique_id}"

        state = create_test_state(
            session_id=session_id,
            user_id=user_id,
            flow_id=flow_id,
            first_message="Test message",
            message_count=5,
        )

        await repo.set(session_id, state)

        response = await client.get(
            "/flows/api/v1/sessions/",
            params={"limit": 200},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 1

        session_ids = [s["session_id"] for s in data["items"]]
        assert session_id in session_ids

        await repo.delete(session_id)

    @pytest.mark.asyncio
    async def test_list_sessions_with_user_filter(self, client, app, unique_id):
        """GET /api/v1/sessions с фильтром по user_id."""
        container = get_container()
        repo = container.state_repository

        target_user = f"target_user_{unique_id}"
        other_user = f"other_user_{unique_id}"

        session1_id = f"flow1_{unique_id}:context1_{unique_id}"
        session2_id = f"flow2_{unique_id}:context2_{unique_id}"

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

        response = await client.get(f"/flows/api/v1/sessions/?user_id={target_user}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["user_id"] == target_user
        assert data["items"][0]["session_id"] == session1_id

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_list_sessions_with_flow_filter(self, client, app, unique_id):
        """GET /api/v1/sessions с фильтром по flow_id."""
        container = get_container()
        repo = container.state_repository

        target_flow = f"target_flow_{unique_id}"
        other_flow = f"other_flow_{unique_id}"

        session1_id = f"{target_flow}:context1_{unique_id}"
        session2_id = f"{other_flow}:context2_{unique_id}"

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

        response = await client.get(f"/flows/api/v1/sessions/?flow_id={target_flow}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["flow_id"] == target_flow

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_list_sessions_with_skill_filter(self, client, app, unique_id):
        """GET /api/v1/sessions с фильтром по branch_id."""
        container = get_container()
        repo = container.state_repository

        flow_id = f"flow_skill_{unique_id}"
        target_skill = f"skill_a_{unique_id}"
        other_skill = f"skill_b_{unique_id}"

        session1_id = f"{flow_id}:context1_{unique_id}"
        session2_id = f"{flow_id}:context2_{unique_id}"

        state1 = create_test_state(
            session_id=session1_id,
            user_id=f"user1_{unique_id}",
            flow_id=flow_id,
            branch_id=target_skill,
        )
        state2 = create_test_state(
            session_id=session2_id,
            user_id=f"user2_{unique_id}",
            flow_id=flow_id,
            branch_id=other_skill,
        )

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)

        response = await client.get(f"/flows/api/v1/sessions/?branch_id={target_skill}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["session_id"] == session1_id

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_list_sessions_with_date_range(self, client, app, unique_id):
        """GET /api/v1/sessions с фильтром по диапазону дат."""
        container = get_container()
        repo = container.state_repository

        base_user = f"date_test_user_{unique_id}"
        now = datetime.now(timezone.utc)
        date_from = (now - timedelta(days=2)).replace(tzinfo=None).isoformat()
        date_to = (now - timedelta(days=1)).replace(tzinfo=None).isoformat()

        session_old_id = f"flow1_{unique_id}:context_old_{unique_id}"
        session_in_range_id = f"flow2_{unique_id}:context_in_range_{unique_id}"
        session_new_id = f"flow3_{unique_id}:context_new_{unique_id}"

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

        # Обновляем created_at напрямую в БД для тестирования фильтров по дате
        from sqlalchemy import update

        from apps.flows.src.db.models import States

        key_old = repo._build_final_key(repo._get_key(session_old_id))
        key_in_range = repo._build_final_key(repo._get_key(session_in_range_id))
        key_new = repo._build_final_key(repo._get_key(session_new_id))

        date_old = (now - timedelta(days=3)).replace(tzinfo=None)
        date_in_range = (now - timedelta(days=1, hours=12)).replace(tzinfo=None)
        date_new = now.replace(tzinfo=None)

        async with container.storage.get_session() as session:
            await session.execute(
                update(States)
                .where(States.key == key_old)
                .values(created_at=date_old, updated_at=date_old)
            )
            await session.execute(
                update(States)
                .where(States.key == key_in_range)
                .values(created_at=date_in_range, updated_at=date_in_range)
            )
            await session.execute(
                update(States)
                .where(States.key == key_new)
                .values(created_at=date_new, updated_at=date_new)
            )
            await session.commit()

        response = await client.get(
            f"/flows/api/v1/sessions/?user_id={base_user}&date_from={date_from}&date_to={date_to}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["session_id"] == session_in_range_id

        await repo.delete(session_old_id)
        await repo.delete(session_in_range_id)
        await repo.delete(session_new_id)

    @pytest.mark.asyncio
    async def test_list_sessions_with_combined_filters(self, client, app, unique_id):
        """GET /api/v1/sessions с комбинацией фильтров."""
        container = get_container()
        repo = container.state_repository

        target_user = f"target_user_{unique_id}"
        target_flow = f"target_flow_{unique_id}"

        session1_id = f"{target_flow}:context1_{unique_id}"
        session2_id = f"other_flow_{unique_id}:context2_{unique_id}"

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

        await repo.set(session1_id, state1)
        await repo.set(session2_id, state2)

        response = await client.get(
            f"/flows/api/v1/sessions/?user_id={target_user}&flow_id={target_flow}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["session_id"] == session1_id

        await repo.delete(session1_id)
        await repo.delete(session2_id)

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, client, app, unique_id):
        """GET /api/v1/sessions с пагинацией."""
        container = get_container()
        repo = container.state_repository

        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"

        for i in range(5):
            session_id = f"{flow_id}:context_{i}_{unique_id}"
            state = create_test_state(
                session_id=session_id,
                user_id=base_user,
                flow_id=flow_id,
            )
            await repo.set(session_id, state)

        response1 = await client.get(
            f"/flows/api/v1/sessions/?user_id={base_user}&limit=2&offset=0"
        )
        response2 = await client.get(
            f"/flows/api/v1/sessions/?user_id={base_user}&limit=2&offset=2"
        )

        assert response1.status_code == 200
        assert response2.status_code == 200

        data1 = response1.json()
        data2 = response2.json()

        assert data1["total"] == data2["total"] == 5
        assert len(data1["items"]) == 2
        assert len(data2["items"]) == 2

        page1_ids = {s["session_id"] for s in data1["items"]}
        page2_ids = {s["session_id"] for s in data2["items"]}
        assert page1_ids.isdisjoint(page2_ids)

        for i in range(5):
            session_id = f"{flow_id}:context_{i}_{unique_id}"
            await repo.delete(session_id)

    @pytest.mark.asyncio
    async def test_list_sessions_empty_result(self, client, app, unique_id):
        """GET /api/v1/sessions с фильтрами, которые не дают результатов."""
        response = await client.get(
            f"/flows/api/v1/sessions/?user_id=nonexistent_user_{unique_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_list_sessions_response_structure(self, client, app, unique_id):
        """Проверка структуры ответа API."""
        container = get_container()
        repo = container.state_repository

        flow_id = f"flow_{unique_id}"
        user_id = f"user_{unique_id}"
        session_id = f"{flow_id}:context_{unique_id}"

        state = create_test_state(
            session_id=session_id,
            user_id=user_id,
            flow_id=flow_id,
            first_message="Hello world",
            message_count=10,
        )

        await repo.set(session_id, state)

        response = await client.get(f"/flows/api/v1/sessions/?user_id={user_id}")

        assert response.status_code == 200
        data = response.json()

        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data

        session_data = data["items"][0]
        assert session_data["session_id"] == session_id
        assert session_data["channel"] == "a2a"
        assert session_data["user_id"] == user_id
        assert session_data["flow_id"] == flow_id
        assert session_data["message_count"] == 10
        assert session_data["first_message"] == "Hello world"
        assert "status" in session_data
        assert "created_at" in session_data
        assert "last_activity" in session_data

        await repo.delete(session_id)

    @pytest.mark.asyncio
    async def test_list_sessions_limit_validation(self, client, app):
        """Проверка валидации параметра limit."""
        response = await client.get("/flows/api/v1/sessions/?limit=0")
        assert response.status_code == 422

        response = await client.get("/flows/api/v1/sessions/?limit=501")
        assert response.status_code == 422

        response = await client.get("/flows/api/v1/sessions/?limit=50")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_sessions_offset_validation(self, client, app):
        """Проверка валидации параметра offset."""
        response = await client.get("/flows/api/v1/sessions/?offset=-1")
        assert response.status_code == 422

        response = await client.get("/flows/api/v1/sessions/?offset=0")
        assert response.status_code == 200

