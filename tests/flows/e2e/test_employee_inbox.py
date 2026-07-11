"""Единый inbox «платформа → flow-сотрудник» (`api/v1/internal_employee_inbox.py`).

Реальный ASGI + signed internal headers; провижн сотрудника через Flows API.
Проверяется контракт enqueue, резолв identity (context_id, flow_id) и ветки Zero-Guess.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from core.identity.flow_employee import flow_employee_user_id
from core.internal_context_headers import build_internal_context_headers
from core.models.identity_models import User

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


def _internal_client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_sync_message_enqueues(app, client, unique_id, system_user_id):
    flow_id = f"inbox_sync_{unique_id}"
    await _provision_employee_flow(client, flow_id, system_user_id)
    emp_id = flow_employee_user_id(flow_id)
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)

    async with _internal_client(app) as http:
        resp = await http.post(
            "/flows/api/v1/internal/employee/inbox",
            headers=headers,
            json={
                "source": "sync_message",
                "company_id": "system",
                "employee_user_id": emp_id,
                "sender_user_id": system_user_id,
                "channel_id": "chan1",
                "message_id": "m1",
                "text": "hello employee",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "enqueued"
    assert body["flow_id"] == flow_id
    assert body["context_id"] == "sync:chan1"

    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_work_item_assigned_enqueues(app, client, unique_id, system_user_id):
    flow_id = f"inbox_wi_{unique_id}"
    await _provision_employee_flow(client, flow_id, system_user_id)
    emp_id = flow_employee_user_id(flow_id)
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)

    async with _internal_client(app) as http:
        resp = await http.post(
            "/flows/api/v1/internal/employee/inbox",
            headers=headers,
            json={
                "source": "work_item_assigned",
                "company_id": "system",
                "employee_user_id": emp_id,
                "sender_user_id": system_user_id,
                "work_item_id": "wi-123",
                "text": "do the task",
                "branch_id": "default",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["context_id"] == "work_item:wi-123"

    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_not_flow_employee_ignored(app, container, unique_id, system_user_id):
    # обычный пользователь, не сотрудник-агент
    plain_id = f"plain_{unique_id}"
    plain = User(
        user_id=plain_id,
        name="Plain",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    await container.user_repository.set(plain)
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)

    async with _internal_client(app) as http:
        resp = await http.post(
            "/flows/api/v1/internal/employee/inbox",
            headers=headers,
            json={
                "source": "sync_message",
                "company_id": "system",
                "employee_user_id": plain_id,
                "sender_user_id": system_user_id,
                "channel_id": "c",
                "message_id": "m",
                "text": "t",
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"status": "ignored", "reason": "not_flow_employee"}
    await container.user_repository.delete(plain_id)


async def test_unknown_employee_errors(app, unique_id, system_user_id):
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)
    async with _internal_client(app) as http:
        resp = await http.post(
            "/flows/api/v1/internal/employee/inbox",
            headers=headers,
            json={
                "source": "sync_message",
                "company_id": "system",
                "employee_user_id": f"flow_employee_missing_{unique_id}",
                "sender_user_id": system_user_id,
                "channel_id": "c",
                "message_id": "m",
                "text": "t",
            },
        )
    assert resp.status_code == 500, resp.text


async def test_unknown_source_422(app, unique_id, system_user_id):
    headers = build_internal_context_headers(company_id="system", user_id=system_user_id)
    async with _internal_client(app) as http:
        resp = await http.post(
            "/flows/api/v1/internal/employee/inbox",
            headers=headers,
            json={
                "source": "telepathy",
                "company_id": "system",
                "employee_user_id": "flow_employee_x",
                "sender_user_id": system_user_id,
                "text": "t",
            },
        )
    assert resp.status_code == 422, resp.text
