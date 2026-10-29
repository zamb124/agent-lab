"""Тесты Sessions API поверх durable workflow ledger."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from apps.flows.src.durable_execution import (
    UserInputAppliedPayload,
    WorkflowEventType,
    create_initial_state,
)
from apps.flows.src.durable_execution.models import (
    WorkflowEvent,
    WorkflowInstance,
    WorkflowSnapshot,
)
from core.context import require_active_company
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

    from a2a.types import Message, Part
    from a2a.types.a2a_pb2 import (
        ROLE_AGENT,
        ROLE_USER,
    )

    messages = []
    if first_message:
        messages.append(
            Message(
                message_id="msg1",
                role=ROLE_USER,
                parts=[Part(text=first_message)],
                task_id=task_id,
            )
        )

    for i in range(max(0, message_count - (1 if first_message else 0))):
        role = ROLE_AGENT if i % 2 == 0 else ROLE_USER
        messages.append(
            Message(
                message_id=f"msg{i + 2}",
                role=role,
                parts=[Part(text=f"Message {i + 2}")],
                task_id=task_id,
            )
        )

    state.messages = messages
    return state


async def save_test_state(state: ExecutionState, di) -> None:
    await di.workflow_runtime.save_state(
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


async def set_instance_time(session_id: str, updated_at: datetime, di) -> None:
    _ = di
    company_id = require_active_company().company_id
    _ = await WorkflowInstance.objects.filter(
        company_id=company_id,
        session_id=session_id,
    ).update(
        returning=False,
        using="flows",
        created_at=updated_at,
        updated_at=updated_at,
    )


class TestSessionsAPI:
    @pytest.mark.asyncio
    async def test_list_sessions(self, client, app, unique_id, di):
        _ = app
        flow_id = f"flow_{unique_id}"
        user_id = f"user_{unique_id}"
        session_id = f"{flow_id}:context_{unique_id}"

        await save_test_state(
            create_test_state(
                session_id,
                user_id,
                first_message="Test message",
                message_count=5,
            ),
        di=di)

        response = await client.get("/flows/api/v1/sessions/", params={"limit": 200})

        assert response.status_code == 200
        data = response.json()
        assert {"items", "total", "limit", "offset"} <= set(data)
        assert session_id in [s["session_id"] for s in data["items"]]

    @pytest.mark.asyncio
    async def test_list_sessions_with_user_filter(self, client, app, unique_id, di):
        _ = app
        target_user = f"target_user_{unique_id}"
        session1_id = f"flow1_{unique_id}:context1_{unique_id}"
        session2_id = f"flow2_{unique_id}:context2_{unique_id}"

        await save_test_state(create_test_state(session1_id, target_user), di=di)
        await save_test_state(create_test_state(session2_id, f"other_user_{unique_id}"), di=di)

        response = await client.get(f"/flows/api/v1/sessions/?user_id={target_user}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["user_id"] == target_user
        assert data["items"][0]["session_id"] == session1_id

    @pytest.mark.asyncio
    async def test_list_sessions_with_flow_filter(self, client, app, unique_id, di):
        _ = app
        target_flow = f"target_flow_{unique_id}"
        other_flow = f"other_flow_{unique_id}"
        session1_id = f"{target_flow}:context1_{unique_id}"
        session2_id = f"{other_flow}:context2_{unique_id}"

        await save_test_state(create_test_state(session1_id, f"user1_{unique_id}"), di=di)
        await save_test_state(create_test_state(session2_id, f"user2_{unique_id}"), di=di)

        response = await client.get(f"/flows/api/v1/sessions/?flow_id={target_flow}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["flow_id"] == target_flow

    @pytest.mark.asyncio
    async def test_list_sessions_with_branch_filter(self, client, app, unique_id, di):
        _ = app
        flow_id = f"flow_branch_{unique_id}"
        session1_id = f"{flow_id}:context1_{unique_id}"
        session2_id = f"{flow_id}:context2_{unique_id}"
        branch_a = f"branch-a-{unique_id}"
        branch_b = f"branch-b-{unique_id}"

        await save_test_state(
            create_test_state(session1_id, f"user1_{unique_id}", branch_id=branch_a),
        di=di)
        await save_test_state(
            create_test_state(session2_id, f"user2_{unique_id}", branch_id=branch_b),
        di=di)

        response = await client.get("/flows/api/v1/sessions/", params={"branch_id": branch_a})

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["session_id"] == session1_id

    @pytest.mark.asyncio
    async def test_list_sessions_with_date_range(self, client, app, unique_id, di):
        _ = app
        base_user = f"date_test_user_{unique_id}"
        now = datetime.now(timezone.utc)
        date_from = now - timedelta(days=2)
        date_to = now - timedelta(days=1)

        session_old_id = f"flow1_{unique_id}:context_old_{unique_id}"
        session_in_range_id = f"flow2_{unique_id}:context_in_range_{unique_id}"
        session_new_id = f"flow3_{unique_id}:context_new_{unique_id}"

        await save_test_state(create_test_state(session_old_id, base_user), di=di)
        await save_test_state(create_test_state(session_in_range_id, base_user), di=di)
        await save_test_state(create_test_state(session_new_id, base_user), di=di)

        await set_instance_time(session_old_id, now - timedelta(days=3), di=di)
        await set_instance_time(session_in_range_id, date_from + timedelta(hours=12), di=di)
        await set_instance_time(session_new_id, now, di=di)

        response = await client.get(
            "/flows/api/v1/sessions/",
            params={
                "user_id": base_user,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["session_id"] == session_in_range_id

    @pytest.mark.asyncio
    async def test_list_sessions_with_combined_filters(self, client, app, unique_id, di):
        _ = app
        target_user = f"target_user_{unique_id}"
        target_flow = f"target_flow_{unique_id}"
        session1_id = f"{target_flow}:context1_{unique_id}"
        session2_id = f"other_flow_{unique_id}:context2_{unique_id}"

        await save_test_state(create_test_state(session1_id, target_user), di=di)
        await save_test_state(create_test_state(session2_id, target_user), di=di)

        response = await client.get(
            "/flows/api/v1/sessions/",
            params={"user_id": target_user, "flow_id": target_flow},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["session_id"] == session1_id

    @pytest.mark.asyncio
    async def test_list_sessions_pagination(self, client, app, unique_id, di):
        _ = app
        base_user = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"

        for i in range(5):
            await save_test_state(
                create_test_state(f"{flow_id}:context_{i}_{unique_id}", base_user),
            di=di)

        response1 = await client.get(
            "/flows/api/v1/sessions/",
            params={"user_id": base_user, "limit": 2, "offset": 0},
        )
        response2 = await client.get(
            "/flows/api/v1/sessions/",
            params={"user_id": base_user, "limit": 2, "offset": 2},
        )

        assert response1.status_code == 200
        assert response2.status_code == 200
        data1 = response1.json()
        data2 = response2.json()
        assert data1["total"] == data2["total"] == 5
        assert len(data1["items"]) == 2
        assert len(data2["items"]) == 2
        assert {s["session_id"] for s in data1["items"]}.isdisjoint(
            {s["session_id"] for s in data2["items"]}
        )

    @pytest.mark.asyncio
    async def test_list_sessions_skips_projection_hash_mismatch(
        self, client, app, unique_id,
    di):
        _ = app
        user_id = f"user_{unique_id}"
        flow_id = f"flow_{unique_id}"
        good_id = f"{flow_id}:good_{unique_id}"
        bad_id = f"{flow_id}:bad_{unique_id}"
        await save_test_state(
            create_test_state(good_id, user_id, first_message="ok", message_count=2),
        di=di)
        await save_test_state(
            create_test_state(bad_id, user_id, first_message="bad", message_count=2),
        di=di)

        company_id = require_active_company().company_id
        _ = await WorkflowSnapshot.objects.filter(
            company_id=company_id,
            session_id=bad_id,
        ).delete()
        _ = await WorkflowEvent.objects.filter(
            company_id=company_id,
            session_id=bad_id,
        ).update(returning=False, using="flows", next_state_hash="0" * 64)
        _ = await di.a2a_task_projection_service.redis_client.delete(
            f"flows:workflow_projection:{company_id}:{bad_id}"
        )

        response = await client.get(
            "/flows/api/v1/sessions/",
            params={"user_id": user_id, "limit": 200},
        )

        assert response.status_code == 200
        data = response.json()
        session_ids = [item["session_id"] for item in data["items"]]
        assert good_id in session_ids
        assert bad_id not in session_ids

    @pytest.mark.asyncio
    async def test_list_sessions_empty_result(self, client, app, unique_id):
        _ = app
        response = await client.get(
            f"/flows/api/v1/sessions/?user_id=nonexistent_user_{unique_id}"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_sessions_response_structure(self, client, app, unique_id, di):
        _ = app
        flow_id = f"flow_{unique_id}"
        user_id = f"user_{unique_id}"
        session_id = f"{flow_id}:context_{unique_id}"

        await save_test_state(
            create_test_state(
                session_id,
                user_id,
                first_message="Hello world",
                message_count=10,
            ),
        di=di)

        response = await client.get(f"/flows/api/v1/sessions/?user_id={user_id}")

        assert response.status_code == 200
        data = response.json()
        assert {"items", "total", "limit", "offset"} <= set(data)

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

    @pytest.mark.asyncio
    async def test_list_sessions_limit_validation(self, client, app):
        _ = app
        response = await client.get("/flows/api/v1/sessions/?limit=0")
        assert response.status_code == 422

        response = await client.get("/flows/api/v1/sessions/?limit=501")
        assert response.status_code == 422

        response = await client.get("/flows/api/v1/sessions/?limit=50")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_delete_session(self, client, app, unique_id, di):
        _ = app
        flow_id = f"flow_{unique_id}"
        user_id = f"user_{unique_id}"
        session_id = f"{flow_id}:context_{unique_id}"
        await save_test_state(create_test_state(session_id, user_id), di=di)

        removed = await client.delete(f"/flows/api/v1/sessions/{session_id}")
        assert removed.status_code == 200
        assert removed.json() == {"success": True, "session_id": session_id}

        unknown = await client.delete(f"/flows/api/v1/sessions/{flow_id}:missing_{unique_id}")
        assert unknown.status_code == 404
