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
    from apps.flows.src.models import Edge, FlowConfig, FlowEmployeeConfig
    from core.context import get_context, set_context
    from tests.fixtures.ai_provider_defaults import make_test_company

    container = get_container()
    previous = get_context()
    if previous is None:
        raise RuntimeError("test_context required for flow provision")
    # FlowRepository company-scoped: тот же company_id, что ensure/dispatch
    set_context(
        previous.model_copy(
            update={
                "active_company": make_test_company(
                    company_id=company_id,
                    name=f"Sync employee {company_id}",
                )
            }
        )
    )
    try:
        _ = await container.flow_repository.set(
            FlowConfig(
                flow_id=flow_id,
                name=f"Sync employee {flow_id}",
                entry="main",
                nodes={"main": {"type": "code", "code": "async def run(args, state):\n    return state"}},
                edges=[Edge(from_node="main", to_node=None)],
                employee=FlowEmployeeConfig(enabled=True, roles=["member"], curator_user_ids=[curator_id]),
            )
        )
        _ = await ensure_flow_employee(
            container,
            flow_id=flow_id,
            company_id=company_id,
            name="AI Worker",
            roles=["member"],
            curator_user_ids=[curator_id],
        )
    finally:
        set_context(previous)
    return flow_employee_user_id(flow_id)


async def test_dispatch_to_employee_inbox_succeeds(
    flows_service: object,
    sync_auth_token: str,
    company_id: str,
    sync_user_id: str,
    unique_id: str,
) -> None:
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
        _ = await get_container().user_repository.delete(emp_id)


async def test_human_is_not_flow_employee(
    sync_auth_token: str,
    company_id: str,
    sync_user_id: str,
) -> None:
    _ = sync_auth_token, company_id
    from apps.flows.src.container import get_container

    human = await get_container().user_repository.get(sync_user_id)
    assert human is not None
    # обычный пользователь не сотрудник-агент — диспатча в inbox для него нет
    assert is_flow_employee(human) is False
