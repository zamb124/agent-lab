"""Кросс-сервисная атрибуция identity сотрудника-агента.

Сотрудник исполняется под собственным SESSION JWT — peer-сервис (CRM) видит
обычного пользователя ``flow_employee_{id}`` без адаптеров. Реальные flows+crm.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from core.clients.service_client import ServiceClient
from core.context import clear_context, get_context, set_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
)

pytestmark = pytest.mark.asyncio


@contextmanager
def _context(ctx):
    previous = get_context()
    set_context(ctx)
    try:
        yield
    finally:
        if previous is None:
            clear_context()
        else:
            set_context(previous)


async def test_peer_service_sees_employee_identity(
    flows_service,
    crm_service,
    frontend_container,
    unique_id,
    system_user_id,
):
    _ = flows_service, crm_service
    flow_id = f"prop_flow_{unique_id}"
    company = await frontend_container.company_repository.get("system")
    assert company is not None

    employee = await ensure_flow_employee(
        frontend_container,
        flow_id=flow_id,
        company_id="system",
        name="AI Worker",
        roles=["member", "admin"],
        curator_user_ids=[system_user_id],
    )
    emp_id = flow_employee_user_id(flow_id)
    try:
        employee_ctx = build_job_context(
            company=company,
            user=employee,
            host="",
            trace_id=f"trace_{unique_id}",
            session_id=f"{flow_id}:ctx",
            channel="a2a",
        )
        client = ServiceClient()
        with _context(employee_ctx):
            created = await client.post(
                "crm",
                "/crm/api/v1/entities",
                json={
                    "entity_type": "contact",
                    "name": f"Contact {unique_id}",
                    "namespace": "default",
                },
            )
            assert isinstance(created, dict), created
            entity_id = created["entity_id"]
            assert entity_id

            # сотрудник (owner) читает созданную сущность под собственным JWT
            fetched = await client.get("crm", f"/crm/api/v1/entities/{entity_id}")
            assert isinstance(fetched, dict)
            assert fetched["entity_id"] == entity_id
            assert fetched["user_id"] == emp_id
    finally:
        await deactivate_flow_employee(frontend_container, flow_id=flow_id, company_id="system")
        await frontend_container.user_repository.delete(emp_id)
