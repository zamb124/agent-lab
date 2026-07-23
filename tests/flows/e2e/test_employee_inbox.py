"""Единый inbox «платформа → flow-сотрудник» (`EmployeeInboxService`).

Вход — consumer group `flows` шины `platform:events`; здесь проверяется сам
сервис: контракт enqueue, резолв identity (context_id, flow_id), write-back
в WorkItem (FlowSessionLink + системный комментарий) и ветки Zero-Guess.
"""

from __future__ import annotations

import pytest

from core.identity.flow_employee import flow_employee_user_id
from core.models.identity_models import User
from core.worktracker.models import FlowSessionLink, SystemActor

pytestmark = pytest.mark.asyncio

_NODES = {"main": {"type": "llm_node", "prompt": "hi"}}


async def _provision_employee_flow(client, flow_id: str, curator_id: str) -> None:
    resp = await client.post(
        "/flows/api/v1/flows/",
        json={
            "flow_id": flow_id,
            "name": "Inbox Employee",
            "entry": "main",
            "nodes": _NODES,
            "edges": [],
            "employee": {
                "enabled": True,
                "roles": ["member"],
                "curator_user_ids": [curator_id],
            },
        },
    )
    assert resp.status_code == 200, resp.text


async def test_sync_message_enqueues(app, client, container, unique_id, system_user_id):
    _ = app
    flow_id = f"inbox_sync_{unique_id}"
    await _provision_employee_flow(client, flow_id, system_user_id)
    emp_id = flow_employee_user_id(flow_id)

    dispatched = await container.employee_inbox_service.dispatch_sync_message(
        company_id="system",
        employee_user_id=emp_id,
        sender_user_id=system_user_id,
        channel_id="chan1",
        message_id="m1",
        text="hello employee",
    )
    assert dispatched is True

    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_work_item_assigned_enqueues_with_write_back(
    app, client, container, unique_id, system_user_id
):
    """Enqueue + write-back: FlowSessionLink и системный комментарий на задаче."""
    _ = app
    flow_id = f"inbox_wi_{unique_id}"
    await _provision_employee_flow(client, flow_id, system_user_id)
    emp_id = flow_employee_user_id(flow_id)

    work_item = await container.work_item_service.create_manual_task(
        company_id="system",
        title=f"Inbox task {unique_id}",
        created_by=SystemActor(),
    )

    dispatched = await container.employee_inbox_service.dispatch_work_item_assigned(
        company_id="system",
        employee_user_id=emp_id,
        sender_user_id=system_user_id,
        work_item_id=work_item.work_item_id,
        text="do the task",
    )
    assert dispatched is True

    updated = await container.work_item_service.get("system", work_item.work_item_id)
    session_links = [link for link in updated.links if isinstance(link, FlowSessionLink)]
    assert session_links, "ожидался FlowSessionLink после старта employee-run"
    assert session_links[0].session_id == f"{flow_id}:work_item:{work_item.work_item_id}"
    assert session_links[0].flow_id == flow_id

    comments = await container.work_item_service.list_comments(
        "system", work_item.work_item_id
    )
    assert any("Агент взял задачу" in comment.text for comment in comments)

    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_not_flow_employee_ignored(app, container, unique_id, system_user_id):
    """Обычный пользователь, не сотрудник-агент — диспатч игнорируется."""
    _ = app
    plain_id = f"plain_{unique_id}"
    plain = User(
        user_id=plain_id,
        name="Plain",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    await container.user_repository.set(plain)

    dispatched = await container.employee_inbox_service.dispatch_sync_message(
        company_id="system",
        employee_user_id=plain_id,
        sender_user_id=system_user_id,
        channel_id="c",
        message_id="m",
        text="t",
    )
    assert dispatched is False
    await container.user_repository.delete(plain_id)


async def test_unknown_employee_errors(app, container, unique_id, system_user_id):
    _ = app
    with pytest.raises(ValueError, match="not found"):
        _ = await container.employee_inbox_service.dispatch_sync_message(
            company_id="system",
            employee_user_id=f"flow_employee_missing_{unique_id}",
            sender_user_id=system_user_id,
            channel_id="c",
            message_id="m",
            text="t",
        )
