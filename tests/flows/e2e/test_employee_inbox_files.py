"""Inbox кладёт вложения источника в files сессии без отбора по типу."""

from __future__ import annotations

import pytest
from httpx2 import AsyncClient

from apps.flows.di import FlowsDi
from apps.flows.src.services.employee_inbox_service import EmployeeInboxService
from core.files.file_ref import FileRef
from core.identity.flow_employee import flow_employee_user_id
from core.worktracker.models import SystemActor

pytestmark = pytest.mark.asyncio

_NODES = {"main": {"type": "llm_node", "prompt": "hi"}}


async def _provision_employee_flow(client: AsyncClient, flow_id: str, curator_id: str) -> None:
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


async def test_work_item_assigned_puts_attachments_on_session(
    app: object,
    client: AsyncClient,
    di: FlowsDi,
    unique_id: str,
    system_user_id: str,
) -> None:
    """Фото и прочий файл задачи оба попадают в state.files."""
    _ = app
    flow_id = f"inbox_files_{unique_id}"
    await _provision_employee_flow(client, flow_id, system_user_id)
    emp_id = flow_employee_user_id(flow_id)
    file_id = f"menu_{unique_id}"
    note_id = f"note_{unique_id}"

    work_item = await di.work_item_service.create_manual_task(
        company_id="system",
        title=f"Inbox files {unique_id}",
        created_by=SystemActor(),
        attachments=[
            FileRef(
                file_id=file_id,
                original_name=f"menu-{unique_id}.jpg",
                content_type="image/jpeg",
                file_size=4,
            ),
            FileRef(
                file_id=note_id,
                original_name=f"note-{unique_id}.txt",
                content_type="text/plain",
                file_size=2,
            ),
        ],
    )

    dispatched = await EmployeeInboxService(di.work_item_service).dispatch_work_item_assigned(
        company_id="system",
        employee_user_id=emp_id,
        sender_user_id=system_user_id,
        work_item_id=work_item.work_item_id,
        text="import the menu",
    )
    assert dispatched is True

    state = await di.workflow_runtime.get_state(
        f"{flow_id}:work_item:{work_item.work_item_id}"
    )
    assert state is not None
    assert {ref.file_id for ref in state.files} == {file_id, note_id}

    _ = await client.delete(f"/flows/api/v1/flows/{flow_id}")
