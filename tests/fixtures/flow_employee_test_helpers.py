"""Provision flow-сотрудника в shared/flows БД для интеграционных тестов."""

from __future__ import annotations

from apps.flows.src.models import Edge, FlowConfig, FlowEmployeeConfig
from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
)


async def provision_flow_employee_for_tests(
    *,
    flow_id: str,
    curator_user_id: str,
    company_id: str = "system",
) -> str:
    """Сидит минимальный flow + сотрудника; возвращает ``flow_employee_user_id``."""
    from apps.flows.src.container import get_container

    container = get_container()
    flow_config = FlowConfig(
        flow_id=flow_id,
        name=f"Test flow {flow_id}",
        entry="main",
        nodes={
            "main": {
                "type": "code",
                "code": "async def run(args, state):\n    return state",
            }
        },
        edges=[Edge(from_node="main", to_node=None)],
        employee=FlowEmployeeConfig(
            enabled=True,
            roles=["member"],
            curator_user_ids=[curator_user_id],
        ),
    )
    _ = await container.flow_repository.set(flow_config)
    await container.flow_access_service.sync_flow_saved(
        flow_config,
        company_id=company_id,
        owner_user_id=curator_user_id,
    )
    _ = await ensure_flow_employee(
        container,
        flow_id=flow_id,
        company_id=company_id,
        name=f"AI Worker {flow_id}",
        roles=["member"],
        curator_user_ids=[curator_user_id],
    )
    return flow_employee_user_id(flow_id)


async def cleanup_flow_employee_for_tests(
    *,
    flow_id: str,
    company_id: str = "system",
) -> None:
    from apps.flows.src.container import get_container

    container = get_container()
    await deactivate_flow_employee(container, flow_id=flow_id, company_id=company_id)
    emp_id = flow_employee_user_id(flow_id)
    _ = await container.user_repository.delete(emp_id)
    await container.flow_access_service.sync_flow_deleted(
        flow_id, company_id=company_id, branch_ids=[]
    )
    _ = await container.flow_repository.delete(flow_id)


__all__ = [
    "cleanup_flow_employee_for_tests",
    "provision_flow_employee_for_tests",
]
