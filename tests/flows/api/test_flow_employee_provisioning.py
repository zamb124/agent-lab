"""Provisioning сотрудника-агента через Flows API (create/update/delete).

Реальный HTTP через `client` (auth system), состояние — через flows `container`.
"""

from __future__ import annotations

import pytest

from core.identity.flow_employee import flow_employee_user_id, is_flow_employee
from core.models.identity_models import UserStatus

pytestmark = pytest.mark.asyncio

_NODES = {"main": {"type": "llm_node", "prompt": "hi"}}


def _create_body(flow_id: str, *, employee: dict | None = None) -> dict:
    body = {
        "flow_id": flow_id,
        "name": "Employee Flow",
        "entry": "main",
        "nodes": _NODES,
        "edges": [],
    }
    if employee is not None:
        body["employee"] = employee
    return body


async def test_create_with_employee_provisions_user(client, container, unique_id, system_user_id):
    flow_id = f"emp_prov_{unique_id}"
    resp = await client.post(
        "/flows/api/v1/flows/",
        json=_create_body(
            flow_id,
            employee={
                "enabled": True,
                "roles": ["member"],
                "curator_user_ids": [system_user_id],
            },
        ),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["employee"]["enabled"] is True

    emp_id = flow_employee_user_id(flow_id)
    user = await container.user_repository.get(emp_id)
    assert user is not None
    assert is_flow_employee(user)
    assert user.status == UserStatus.ACTIVE
    assert "member" in user.companies["system"]

    company = await container.company_repository.get("system")
    assert company is not None
    assert emp_id in company.members

    await client.delete(f"/flows/api/v1/flows/{flow_id}")
    company_after = await container.company_repository.get("system")
    assert company_after is not None
    assert emp_id not in company_after.members
    user_after = await container.user_repository.get(emp_id)
    assert user_after is not None
    assert user_after.status == UserStatus.INACTIVE


async def test_update_toggles_employee(client, container, unique_id, system_user_id):
    flow_id = f"emp_toggle_{unique_id}"
    emp_id = flow_employee_user_id(flow_id)

    create = await client.post("/flows/api/v1/flows/", json=_create_body(flow_id))
    assert create.status_code == 200

    # включаем employee
    on = await client.put(
        f"/flows/api/v1/flows/{flow_id}",
        json=_create_body(
            flow_id,
            employee={
                "enabled": True,
                "roles": ["member", "flow_operator"],
                "curator_user_ids": [system_user_id],
                "avatar_url": "https://example.com/a.png",
            },
        ),
    )
    assert on.status_code == 200
    user = await container.user_repository.get(emp_id)
    assert user is not None and user.status == UserStatus.ACTIVE
    assert user.avatar_url == "https://example.com/a.png"
    assert set(user.companies["system"]) == {"member", "flow_operator"}

    # выключаем
    off = await client.put(f"/flows/api/v1/flows/{flow_id}", json=_create_body(flow_id))
    assert off.status_code == 200
    user_off = await container.user_repository.get(emp_id)
    assert user_off is not None and user_off.status == UserStatus.INACTIVE

    await client.delete(f"/flows/api/v1/flows/{flow_id}")


async def test_create_employee_enabled_without_roles_422(client, unique_id, system_user_id):
    flow_id = f"emp_invalid_{unique_id}"
    resp = await client.post(
        "/flows/api/v1/flows/",
        json=_create_body(
            flow_id,
            employee={"enabled": True, "roles": [], "curator_user_ids": [system_user_id]},
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_create_employee_enabled_without_curators_422(client, unique_id):
    flow_id = f"emp_invalid2_{unique_id}"
    resp = await client.post(
        "/flows/api/v1/flows/",
        json=_create_body(
            flow_id,
            employee={"enabled": True, "roles": ["member"], "curator_user_ids": []},
        ),
    )
    assert resp.status_code == 422, resp.text


async def test_employee_not_visible_in_other_company_members(
    client,
    frontend_client,
    unique_id,
    system_user_id,
    auth_headers_system,
    auth_headers_company2,
):
    flow_id = f"emp_iso_{unique_id}"
    emp_id = flow_employee_user_id(flow_id)
    create = await client.post(
        "/flows/api/v1/flows/",
        json=_create_body(
            flow_id,
            employee={
                "enabled": True,
                "roles": ["member"],
                "curator_user_ids": [system_user_id],
            },
        ),
    )
    assert create.status_code == 200, create.text
    try:
        system_members = await frontend_client.get(
            "/frontend/api/team/members",
            headers=auth_headers_system,
        )
        assert system_members.status_code == 200
        assert emp_id in {m["user_id"] for m in system_members.json()["items"]}

        other_members = await frontend_client.get(
            "/frontend/api/team/members",
            headers=auth_headers_company2,
        )
        assert other_members.status_code == 200
        assert emp_id not in {m["user_id"] for m in other_members.json()["items"]}
    finally:
        await client.delete(f"/flows/api/v1/flows/{flow_id}")
