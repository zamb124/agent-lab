"""Team API: members badge + act-as flow-сотрудника (`core/api/team.py`).

Реальный frontend ASGI + реальные репозитории. Провижн сотрудника через
`ensure_flow_employee`; teardown снимает членство и запись.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from core.identity.flow_employee import (
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_user_id,
)
from core.utils.tokens import get_token_service
from tests.fixtures.auth import set_test_company_member_roles

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def _ensure_system_team_members(
    frontend_container, system_user_id, system_user2_id
) -> None:
    """Под -n10 другие тесты могут перезаписать company.members — восстанавливаем session users."""
    company = await frontend_container.company_repository.get("system")
    if company is None:
        raise RuntimeError("system company отсутствует в тестовой БД")
    if system_user_id not in company.members:
        await set_test_company_member_roles(
            frontend_container.company_repository,
            frontend_container.authz_service,
            company_id="system",
            user_id=system_user_id,
            roles=["owner", "admin"],
        )
    if system_user2_id not in company.members:
        await set_test_company_member_roles(
            frontend_container.company_repository,
            frontend_container.authz_service,
            company_id="system",
            user_id=system_user2_id,
            roles=["member"],
        )


async def _cleanup_employee(frontend_container, flow_id: str) -> None:
    await deactivate_flow_employee(frontend_container, flow_id=flow_id, company_id="system")
    await frontend_container.user_repository.delete(flow_employee_user_id(flow_id))


@pytest_asyncio.fixture
async def employee_with_curator(frontend_container, unique_id, system_user2_id):
    """Сотрудник-агент system с куратором = system_user2 (member, не admin)."""
    flow_id = f"team_emp_{unique_id}"
    await ensure_flow_employee(
        frontend_container,
        flow_id=flow_id,
        company_id="system",
        name="AI Worker",
        roles=["member"],
        curator_user_ids=[system_user2_id],
    )
    yield flow_id, flow_employee_user_id(flow_id)
    await _cleanup_employee(frontend_container, flow_id)


async def test_members_badge_fields(
    frontend_client, employee_with_curator, auth_headers_system, system_user2_id
):
    _flow_id, emp_id = employee_with_curator
    resp = await frontend_client.get("/frontend/api/team/members", headers=auth_headers_system)
    assert resp.status_code == 200, resp.text
    by_id = {m["user_id"]: m for m in resp.json()["items"]}
    assert emp_id in by_id
    emp = by_id[emp_id]
    assert emp["is_flow_employee"] is True
    assert emp["flow_id"] == _flow_id
    assert emp["curator_user_ids"] == [system_user2_id]
    # обычный пользователь без бейджа
    assert by_id[system_user2_id]["is_flow_employee"] is False


async def test_act_as_by_admin(
    frontend_client, employee_with_curator, auth_headers_system, system_user_id
):
    _flow_id, emp_id = employee_with_curator
    resp = await frontend_client.post(
        f"/frontend/api/team/employees/{emp_id}/act-as", headers=auth_headers_system
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["impersonated_by"] == system_user_id

    token = resp.cookies.get("auth_token")
    assert token
    td = get_token_service().validate_token(token)
    assert td is not None
    assert td.user_id == emp_id
    assert td.metadata.get("impersonated_by") == system_user_id
    assert (td.exp - td.iat).total_seconds() <= 3600


async def test_act_as_by_curator(
    frontend_client, employee_with_curator, auth_headers_system_user2
):
    _flow_id, emp_id = employee_with_curator
    resp = await frontend_client.post(
        f"/frontend/api/team/employees/{emp_id}/act-as", headers=auth_headers_system_user2
    )
    assert resp.status_code == 200, resp.text


async def test_act_as_non_curator_member_403(
    frontend_client, frontend_container, unique_id, auth_headers_system_user2, system_user_id
):
    # куратор = admin (system_user_id), вызывает member (system_user2) → не куратор, не admin
    flow_id = f"team_emp_b_{unique_id}"
    await ensure_flow_employee(
        frontend_container,
        flow_id=flow_id,
        company_id="system",
        name="AI Worker B",
        roles=["member"],
        curator_user_ids=[system_user_id],
    )
    emp_id = flow_employee_user_id(flow_id)
    try:
        resp = await frontend_client.post(
            f"/frontend/api/team/employees/{emp_id}/act-as",
            headers=auth_headers_system_user2,
        )
        assert resp.status_code == 403, resp.text
    finally:
        await _cleanup_employee(frontend_container, flow_id)


async def test_act_as_human_target_403(
    frontend_client, auth_headers_system, system_user2_id
):
    resp = await frontend_client.post(
        f"/frontend/api/team/employees/{system_user2_id}/act-as", headers=auth_headers_system
    )
    assert resp.status_code == 403, resp.text


async def test_act_as_unknown_user_404(frontend_client, auth_headers_system, unique_id):
    resp = await frontend_client.post(
        f"/frontend/api/team/employees/flow_employee_ghost_{unique_id}/act-as",
        headers=auth_headers_system,
    )
    assert resp.status_code == 404, resp.text


async def test_stop_act_as_roundtrip(
    frontend_client, employee_with_curator, auth_headers_system, system_user_id
):
    _flow_id, emp_id = employee_with_curator
    act = await frontend_client.post(
        f"/frontend/api/team/employees/{emp_id}/act-as", headers=auth_headers_system
    )
    assert act.status_code == 200
    act_token = act.cookies.get("auth_token")
    assert act_token

    stop = await frontend_client.post(
        "/frontend/api/team/employees/act-as/stop",
        headers={"Authorization": f"Bearer {act_token}"},
    )
    assert stop.status_code == 200, stop.text
    assert stop.json()["user_id"] == system_user_id


async def test_stop_act_as_from_normal_session_409(frontend_client, auth_headers_system):
    resp = await frontend_client.post(
        "/frontend/api/team/employees/act-as/stop", headers=auth_headers_system
    )
    assert resp.status_code == 409, resp.text


async def test_act_as_cross_company_403(
    frontend_client, employee_with_curator, auth_headers_company2
):
    _flow_id, emp_id = employee_with_curator
    resp = await frontend_client.post(
        f"/frontend/api/team/employees/{emp_id}/act-as",
        headers=auth_headers_company2,
    )
    assert resp.status_code == 403, resp.text


async def test_act_as_employee_without_roles_409(
    frontend_client, frontend_container, employee_with_curator, auth_headers_system
):
    _flow_id, emp_id = employee_with_curator
    employee = await frontend_container.user_repository.get(emp_id)
    assert employee is not None
    employee.companies["system"] = []
    await frontend_container.user_repository.set(employee)

    resp = await frontend_client.post(
        f"/frontend/api/team/employees/{emp_id}/act-as",
        headers=auth_headers_system,
    )
    assert resp.status_code == 409, resp.text
