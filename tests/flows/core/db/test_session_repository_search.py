"""Тесты поиска сессий через durable workflow runtime."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from apps.flows.src.container import get_container
from apps.flows.src.db.models import WorkflowInstances
from apps.flows.src.durable_execution import (
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from core.state import ExecutionState


def create_test_state(
    session_id: str,
    user_id: str,
    *,
    first_message: str | None = None,
    message_count: int = 0,
    branch_id: str = "default",
) -> ExecutionState:
    import uuid

    task_id = str(uuid.uuid4())
    context_id = session_id.split(":", 1)[1]
    state = create_initial_state(
        task_id=task_id,
        context_id=context_id,
        user_id=user_id,
        session_id=session_id,
        branch_id=branch_id,
    )

    from a2a.types import Message, Part, Role, TextPart

    messages = []
    if first_message:
        messages.append(
            Message(
                message_id="msg1",
                role=Role.user,
                parts=[Part(root=TextPart(text=first_message))],
                task_id=task_id,
            )
        )

    for i in range(max(0, message_count - (1 if first_message else 0))):
        role = Role.agent if i % 2 == 0 else Role.user
        messages.append(
            Message(
                message_id=f"msg{i + 2}",
                role=role,
                parts=[Part(root=TextPart(text=f"Message {i + 2}"))],
                task_id=task_id,
            )
        )

    state.messages = messages
    return state


async def save_test_state(state: ExecutionState) -> None:
    await get_container().workflow_runtime.save_state(
        state.session_id,
        state,
        event_type=WorkflowEventType.user_input_applied,
        payload=UserInputAppliedPayload(
            task_id=state.task_id,
            context_id=state.context_id,
            is_resume=False,
        ),
        snapshot=True,
    )


async def set_instance_time(session_id: str, updated_at: datetime) -> None:
    container = get_container()
    async with container.storage.get_session() as session:
        await session.execute(
            update(WorkflowInstances)
            .where(WorkflowInstances.session_id == session_id)
            .values(created_at=updated_at, updated_at=updated_at)
        )
        await session.commit()


class TestDurableWorkflowSessionSearch:
    @pytest.mark.asyncio
    async def test_search_all_sessions(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        session1_id = f"flow1_{unique_id}:session1_{unique_id}"
        session2_id = f"flow2_{unique_id}:session2_{unique_id}"

        await save_test_state(
            create_test_state(
                session1_id,
                f"user1_{unique_id}",
                first_message="Hello",
                message_count=5,
            )
        )
        await save_test_state(
            create_test_state(
                session2_id,
                f"user2_{unique_id}",
                first_message="Hi",
                message_count=10,
            )
        )

        sessions, total = await runtime.search_sessions(limit=500)

        assert total >= 2
        session_ids = [s.session_id for s in sessions]
        assert session1_id in session_ids
        assert session2_id in session_ids

    @pytest.mark.asyncio
    async def test_search_by_user_id(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        target_user = f"target_user_{unique_id}"

        session1_id = f"flow1_{unique_id}:session1_{unique_id}"
        session2_id = f"flow2_{unique_id}:session2_{unique_id}"

        await save_test_state(create_test_state(session1_id, target_user))
        await save_test_state(create_test_state(session2_id, f"other_user_{unique_id}"))

        sessions, total = await runtime.search_sessions(user_id=target_user, limit=100)

        assert total == 1
        assert sessions[0].session_id == session1_id
        assert sessions[0].user_id == target_user

    @pytest.mark.asyncio
    async def test_search_by_flow_id(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        target_flow = f"target_flow_{unique_id}"
        other_flow = f"other_flow_{unique_id}"

        session1_id = f"{target_flow}:session1_{unique_id}"
        session2_id = f"{other_flow}:session2_{unique_id}"

        await save_test_state(create_test_state(session1_id, f"user1_{unique_id}"))
        await save_test_state(create_test_state(session2_id, f"user2_{unique_id}"))

        sessions, total = await runtime.search_sessions(flow_id=target_flow, limit=100)

        assert total == 1
        assert sessions[0].session_id == session1_id
        assert sessions[0].flow_id == target_flow

    @pytest.mark.asyncio
    async def test_search_by_branch_id(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        flow_id = f"branch_flow_{unique_id}"
        target_branch_id = f"branch-a-{unique_id}"
        other_branch_id = f"branch-b-{unique_id}"
        session1_id = f"{flow_id}:session1_{unique_id}"
        session2_id = f"{flow_id}:session2_{unique_id}"

        await save_test_state(
            create_test_state(session1_id, f"user1_{unique_id}", branch_id=target_branch_id)
        )
        await save_test_state(
            create_test_state(session2_id, f"user2_{unique_id}", branch_id=other_branch_id)
        )

        sessions, total = await runtime.search_sessions(branch_id=target_branch_id, limit=100)

        assert total == 1
        assert sessions[0].session_id == session1_id

    @pytest.mark.asyncio
    async def test_search_by_date_range(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
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

        await save_test_state(create_test_state(session_old_id, base_user))
        await save_test_state(create_test_state(session_in_range_id, base_user))
        await save_test_state(create_test_state(session_new_id, base_user))

        await set_instance_time(session_old_id, date_old)
        await set_instance_time(session_in_range_id, date_in_range)
        await set_instance_time(session_new_id, date_new)

        sessions, total = await runtime.search_sessions(
            user_id=base_user,
            date_from=date_from,
            date_to=date_to,
            limit=100,
        )

        assert total == 1
        assert sessions[0].session_id == session_in_range_id

    @pytest.mark.asyncio
    async def test_search_combined_filters(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        target_user = f"target_user_{unique_id}"
        target_flow = f"target_flow_{unique_id}"

        session1_id = f"{target_flow}:session1_{unique_id}"
        session2_id = f"other_flow_{unique_id}:session2_{unique_id}"
        session3_id = f"{target_flow}:session3_{unique_id}"

        await save_test_state(create_test_state(session1_id, target_user))
        await save_test_state(create_test_state(session2_id, target_user))
        await save_test_state(create_test_state(session3_id, f"other_user_{unique_id}"))

        sessions, total = await runtime.search_sessions(
            user_id=target_user,
            flow_id=target_flow,
            limit=100,
        )

        assert total == 1
        assert sessions[0].session_id == session1_id

    @pytest.mark.asyncio
    async def test_search_pagination(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"

        for i in range(5):
            await save_test_state(
                create_test_state(f"{flow_id}:session_{i}_{unique_id}", base_user)
            )

        page1, total1 = await runtime.search_sessions(user_id=base_user, limit=2, offset=0)
        page2, total2 = await runtime.search_sessions(user_id=base_user, limit=2, offset=2)

        assert total1 == total2 == 5
        assert len(page1) == 2
        assert len(page2) == 2
        assert {s.session_id for s in page1}.isdisjoint({s.session_id for s in page2})

    @pytest.mark.asyncio
    async def test_search_empty_result(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime

        sessions, total = await runtime.search_sessions(
            user_id=f"nonexistent_user_{unique_id}",
            limit=100,
        )

        assert total == 0
        assert sessions == []

    @pytest.mark.asyncio
    async def test_search_ordering(self, app, unique_id):
        _ = app
        runtime = get_container().workflow_runtime
        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"
        now = datetime.now(timezone.utc)

        session1_id = f"{flow_id}:session1_{unique_id}"
        session2_id = f"{flow_id}:session2_{unique_id}"
        session3_id = f"{flow_id}:session3_{unique_id}"

        await save_test_state(create_test_state(session1_id, base_user))
        await save_test_state(create_test_state(session2_id, base_user))
        await save_test_state(create_test_state(session3_id, base_user))

        await set_instance_time(session1_id, now - timedelta(hours=2))
        await set_instance_time(session2_id, now - timedelta(hours=1))
        await set_instance_time(session3_id, now)

        sessions, total = await runtime.search_sessions(user_id=base_user, limit=100)

        assert total == 3
        assert [s.session_id for s in sessions] == [
            session3_id,
            session2_id,
            session1_id,
        ]
