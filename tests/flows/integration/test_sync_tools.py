"""Builtin sync-тулы сотрудника-агента (`apps/flows/tools/sync/sync_tools.py`).

Сотрудник действует от собственного имени: ServiceClient шлёт signed internal
headers с его user_id, sync применяет обычный ACL канала. Реальные sync+flows.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from httpx2 import AsyncClient

from apps.flows.src.state import ExecutionState
from apps.flows.tools.sync.sync_tools import sync_list_messages, sync_send_message
from core.clients.service_client import ServiceClientError
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.sync.api._helpers import seed_namespace_via_repo

pytestmark = pytest.mark.asyncio

_SYNC_BASE = "http://127.0.0.1:9005"


def _state(unique_id: str) -> ExecutionState:
    return ExecutionState(
        task_id=f"t-{unique_id}",
        context_id=f"ctx-{unique_id}",
        user_id="actor",
        session_id=f"flow_{unique_id}:ctx",
        branch_id="default",
    )


@contextmanager
def _employee_context(employee_user: User, company):
    previous = get_context()
    employee_ctx = build_job_context(
        company=company,
        user=employee_user,
        host="",
        trace_id="sync-tools-test",
        session_id="s",
        channel="a2a",
    )
    set_context(employee_ctx)
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_sync_send_and_list_as_member(
    flows_service, sync_service, frontend_di, auth_token_system, unique_id
):
    _ = flows_service, sync_service, auth_token_system
    flow_id = f"synctool_{unique_id}"
    company = await Company.get("system")
    assert company is not None
    employee = await ensure_flow_employee(
        frontend_di,
        flow_id=flow_id,
        company_id="system",
        name="Sync Tool Worker",
        roles=["member"],
        curator_user_ids=["system"],
    )
    emp_id = flow_employee_user_id(flow_id)
    assert emp_id == employee.user_id
    namespace = f"ns_{unique_id}_st"
    await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}

    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={"namespace": namespace, "type": "topic", "name": "st_ch", "is_private": False},
        )
        assert cr.status_code == 201, cr.text
        channel_id = cr.json()["channel_id"]
        mr = await http.post(
            f"/sync/api/v1/channels/{channel_id}/members",
            headers=headers,
            json={"user_id": emp_id, "role": "member"},
        )
        assert mr.status_code in (200, 201), mr.text

    with _employee_context(employee, company):
        sent = await sync_send_message.run(
            {"channel_id": channel_id, "text": f"hello from employee {unique_id}"},
            _state(unique_id),
        )
        assert sent["channel_id"] == channel_id
        assert sent["message_id"]

        listed = await sync_list_messages.run({"channel_id": channel_id, "limit": 20}, _state(unique_id))
        assert listed["channel_id"] == channel_id
        assert listed["count"] >= 1


async def test_sync_send_non_member_denied(
    flows_service, sync_service, auth_token_system, unique_id, frontend_di
):
    _ = flows_service, sync_service
    emp_id = f"flow_employee_denied_{unique_id}"
    namespace = f"ns_{unique_id}_dn"
    await seed_namespace_via_repo(frontend_di, "system", namespace)
    headers = {"Authorization": f"Bearer {auth_token_system}"}

    async with AsyncClient(base_url=_SYNC_BASE, timeout=60.0) as http:
        cr = await http.post(
            "/sync/api/v1/channels/",
            headers=headers,
            json={"namespace": namespace, "type": "topic", "name": "dn_ch", "is_private": True},
        )
        assert cr.status_code == 201, cr.text
        channel_id = cr.json()["channel_id"]

    company = make_test_company(company_id="system", name="System")
    outsider = User(
        user_id=emp_id,
        name="Denied Worker",
        companies={"system": ["member"]},
        active_company_id="system",
    )
    with _employee_context(outsider, company):
        with pytest.raises(ServiceClientError):
            await sync_send_message.run(
                {"channel_id": channel_id, "text": "should be denied"},
                _state(unique_id),
            )
