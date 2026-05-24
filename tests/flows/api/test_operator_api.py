"""
Тесты API операторских очередей /flows/api/v1/operator/...
"""

import uuid

import pytest
from a2a.types import Message, Part, Role, TextPart

from apps.flows.src.db.models import OperatorTasks
from apps.flows.src.models.operator_schemas import OperatorTaskStatus
from core.state import ExecutionState


async def _list_all_operator_queues(client, headers: dict) -> list[dict]:
    limit = 200
    offset = 0
    items: list[dict] = []
    while True:
        response = await client.get(
            "/flows/api/v1/operator/queues",
            headers=headers,
            params={"limit": limit, "offset": offset},
        )
        assert response.status_code == 200, response.text
        page = response.json()
        page_items = page["items"]
        items.extend(page_items)
        if len(page_items) < limit:
            return items
        offset += limit


@pytest.mark.asyncio
async def test_operator_create_and_list_queues(client, app, unique_id, auth_headers_system):
    slug = f"opq_{unique_id}"
    create = await client.post(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system,
        json={"name": "Test queue", "slug": slug},
    )
    assert create.status_code == 200, create.text
    data = create.json()
    assert data["slug"] == slug

    queues = await _list_all_operator_queues(client, auth_headers_system)
    assert any(q.get("slug") == slug for q in queues)


@pytest.mark.asyncio
async def test_operator_queues_forbidden_for_member(
    client, app, unique_id, auth_headers_system_user2
):
    slug = f"opq_mem_{unique_id}"
    create = await client.post(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system_user2,
        json={"name": "Member queue try", "slug": slug},
    )
    assert create.status_code == 403, create.text

    lst = await client.get(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system_user2,
    )
    assert lst.status_code == 403, lst.text


@pytest.mark.asyncio
async def test_operator_admin_joins_queue_without_prior_membership(
    client,
    app,
    container,
    unique_id,
    auth_headers_system,
    system_user_id,
):
    slug = f"opq_empty_{unique_id}"
    qid = await container.operator_repository.create_queue(
        company_id="system",
        name="Empty queue",
        slug=slug,
    )
    queues = await _list_all_operator_queues(client, auth_headers_system)
    row = next(q for q in queues if q.get("slug") == slug)
    assert row.get("i_am_member") is False

    add = await client.post(
        f"/flows/api/v1/operator/queues/{qid}/members",
        headers=auth_headers_system,
        json={"user_id": system_user_id, "role": "agent"},
    )
    assert add.status_code == 200, add.text

    queues2 = await _list_all_operator_queues(client, auth_headers_system)
    row2 = next(q for q in queues2 if q.get("slug") == slug)
    assert row2.get("i_am_member") is True


@pytest.mark.asyncio
async def test_operator_member_can_leave_queue(
    client,
    app,
    unique_id,
    auth_headers_system,
    system_user_id,
):
    slug = f"opq_leave_{unique_id}"
    create = await client.post(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system,
        json={"name": "Leave me", "slug": slug},
    )
    assert create.status_code == 200, create.text
    qid = create.json()["id"]

    rm = await client.delete(
        f"/flows/api/v1/operator/queues/{qid}/members/{system_user_id}",
        headers=auth_headers_system,
    )
    assert rm.status_code in (200, 204), rm.text

    queues = await _list_all_operator_queues(client, auth_headers_system)
    row = next(q for q in queues if q.get("slug") == slug)
    assert row.get("i_am_member") is False

    denied = await client.get(
        f"/flows/api/v1/operator/tasks?queue_id={qid}",
        headers=auth_headers_system,
    )
    assert denied.status_code == 403, denied.text


@pytest.mark.asyncio
async def test_operator_list_tasks_empty_for_non_member(
    client, app, unique_id, auth_headers_system, auth_headers_system_user2
):
    slug = f"opq2_{unique_id}"
    create = await client.post(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system,
        json={"name": "Q2", "slug": slug},
    )
    assert create.status_code == 200

    other = await client.get(
        "/flows/api/v1/operator/tasks",
        headers=auth_headers_system_user2,
    )
    assert other.status_code == 200
    body = other.json()
    assert body["items"] == []
    assert body["total"] == 0


@pytest.mark.asyncio
async def test_operator_get_task_includes_message_text_for_a2a_messages(
    client,
    app,
    container,
    unique_id,
    auth_headers_system,
    system_user_id,
) -> None:
    slug = f"opq_msg_{unique_id}"
    create = await client.post(
        "/flows/api/v1/operator/queues",
        headers=auth_headers_system,
        json={"name": "Msg test", "slug": slug},
    )
    assert create.status_code == 200, create.text
    qid = create.json()["id"]

    flow_id = f"fl_op_{unique_id}"
    ctx_id = f"ctx_{unique_id}"
    session_id = f"{flow_id}:{ctx_id}"
    a2a_tid = f"a2a_{unique_id}"
    line = "user line for operator"

    user_msg = Message(
        messageId=str(uuid.uuid4()),
        role=Role.user,
        parts=[Part(root=TextPart(text=line))],
    )
    state = ExecutionState(
        task_id=a2a_tid,
        context_id=ctx_id,
        user_id=system_user_id,
        session_id=session_id,
        messages=[user_msg],
    )
    await container.state_manager.save_state(session_id, state)

    op_task_id = str(uuid.uuid4())
    cor_id = str(uuid.uuid4())
    row = OperatorTasks(
        id=op_task_id,
        company_id="system",
        queue_id=qid,
        status=OperatorTaskStatus.OPEN.value,
        session_id=session_id,
        end_user_id=system_user_id,
        flow_id=flow_id,
        branch_id="default",
        a2a_task_id=a2a_tid,
        context_id=ctx_id,
        correlation_id=cor_id,
        interrupt_snapshot={
            "question": line,
            "task_title": "Msg test",
            "assignee_queue": slug,
            "queue_id": qid,
            "handoff_mode": "single_reply",
        },
    )
    await container.operator_repository.insert_task(row)

    r = await client.get(
        f"/flows/api/v1/operator/tasks/{op_task_id}",
        headers=auth_headers_system,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    dms: list[dict] = data["dialog_messages"]
    assert len(dms) == 1
    assert dms[0]["message_text"] == line
    assert dms[0]["role"] == "user"
