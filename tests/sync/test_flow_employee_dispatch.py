"""Диспатч sync-сообщения сотруднику-агенту через employee inbox flows.

Wake-up flow-сотрудника идёт по событию `sync/message/created` шины
`platform:events`: consumer group `flows` вызывает `EmployeeInboxService`.
Здесь проверяется сам inbox-сервис (резолв сотрудника + enqueue) и то, что
человек сотрудником не является.
"""

from __future__ import annotations

import pytest

from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
    is_flow_employee,
)

pytestmark = pytest.mark.asyncio


async def _provision_employee_flow(company_id: str, flow_id: str, curator_id: str) -> str:
    from apps.flows.src.container import get_container
    from apps.flows.src.models import FlowConfig, FlowEmployeeConfig

    container = get_container()
    await container.flow_repository.set(
        FlowConfig(
            flow_id=flow_id,
            name=f"Sync employee {flow_id}",
            entry="main",
            nodes={"main": {"type": "code", "code": "async def run(args, state):\n    return state"}},
            edges=[{"from_node": "main", "to_node": None}],
            employee=FlowEmployeeConfig(enabled=True, roles=["member"], curator_user_ids=[curator_id]),
        )
    )
    await ensure_flow_employee(
        container,
        flow_id=flow_id,
        company_id=company_id,
        name="AI Worker",
        roles=["member"],
        curator_user_ids=[curator_id],
    )
    return flow_employee_user_id(flow_id)


async def test_dispatch_to_employee_inbox_succeeds(
    flows_service, sync_auth_token, company_id, sync_user_id, unique_id
):
    _ = flows_service, sync_auth_token
    flow_id = f"sync_disp_{unique_id}"
    emp_id = await _provision_employee_flow(company_id, flow_id, curator_id=sync_user_id)
    from apps.flows.src.container import get_container

    try:
        # диспатч проходит без ошибок: inbox нашёл сотрудника и flow, поставил в очередь
        dispatched = await get_container().employee_inbox_service.dispatch_sync_message(
            company_id=company_id,
            employee_user_id=emp_id,
            sender_user_id=sync_user_id,
            channel_id=f"chan_{unique_id}",
            message_id=f"msg_{unique_id}",
            text="employee, please help",
        )
        assert dispatched is True
        # провижн сделал сотрудника обычным участником-User
        employee = await get_container().user_repository.get(emp_id)
        assert employee is not None
        assert is_flow_employee(employee)
    finally:
        await deactivate_flow_employee(get_container(), flow_id=flow_id, company_id=company_id)
        await get_container().user_repository.delete(emp_id)


async def test_human_is_not_flow_employee(
    sync_auth_token, company_id, sync_user_id
):
    _ = sync_auth_token
    from apps.flows.src.container import get_container

    human = await get_container().user_repository.get(sync_user_id)
    assert human is not None
    # обычный пользователь не сотрудник-агент — диспатча в inbox для него нет
    assert is_flow_employee(human) is False
