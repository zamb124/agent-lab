"""Тесты identity-ядра flow-as-employee (`core/identity/flow_employee.py`).

Реальные репозитории (shared user/company) через flows-контейнер, без моков.
Изоляция по `unique_id`; teardown снимает созданные записи.
"""


from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from core.identity.flow_employee import (
    FLOW_EMPLOYEE_KIND,
    deactivate_flow_employee,
    ensure_flow_employee,
    flow_employee_curator_user_ids,
    flow_employee_user_id,
    is_flow_employee,
    is_flow_employee_user_id,
    require_flow_employee_flow_id,
)
from core.models.identity_models import Company, User, UserStatus
from tests.fixtures.ai_provider_defaults import make_test_company
from tests.fixtures.auth import set_test_company_member_roles  # noqa: F401


@pytest_asyncio.fixture
async def employee_company(di, unique_id):
    """Изолированная компания для employee-провижна; teardown чистит запись."""
    company_id = f"emp_co_{unique_id}"
    curator_id = f"curator_{unique_id}"
    company = make_test_company(
        company_id=company_id,
        name="Employee Co",
        owner_user_id=curator_id,
        members={curator_id: ["owner", "admin"]},
    )
    await Company.set(company)
    yield company_id, curator_id
    await Company.delete_by_id(company_id)


# --- Чистые хелперы (без БД) ---


def test_flow_employee_user_id_format():
    assert flow_employee_user_id("my_flow") == "flow_employee_my_flow"
    assert flow_employee_user_id("  spaced  ") == "flow_employee_spaced"


@pytest.mark.parametrize("bad", ["", "   "])
def test_flow_employee_user_id_empty_raises(bad):
    with pytest.raises(ValueError):
        flow_employee_user_id(bad)


def test_is_flow_employee_user_id():
    assert is_flow_employee_user_id("flow_employee_x") is True
    assert is_flow_employee_user_id("regular_user") is False


def test_is_flow_employee_by_attributes():
    emp = User(
        user_id="flow_employee_f1",
        name="Emp",
        attributes={"kind": FLOW_EMPLOYEE_KIND, "flow_id": "f1", "curator_user_ids": ["c1"]},
    )
    human = User(user_id="u1", name="Human")
    assert is_flow_employee(emp) is True
    assert is_flow_employee(human) is False


def test_require_flow_employee_flow_id():
    emp = User(
        user_id="flow_employee_f1",
        name="Emp",
        attributes={"kind": FLOW_EMPLOYEE_KIND, "flow_id": "f1", "curator_user_ids": ["c1"]},
    )
    assert require_flow_employee_flow_id(emp) == "f1"

    human = User(user_id="u1", name="Human")
    with pytest.raises(ValueError):
        require_flow_employee_flow_id(human)

    no_attr = User(user_id="flow_employee_f2", name="Emp", attributes={"kind": FLOW_EMPLOYEE_KIND})
    with pytest.raises(ValueError):
        require_flow_employee_flow_id(no_attr)


def test_flow_employee_curator_user_ids_dedup_and_order():
    emp = User(
        user_id="flow_employee_f1",
        name="Emp",
        attributes={
            "kind": FLOW_EMPLOYEE_KIND,
            "flow_id": "f1",
            "curator_user_ids": ["c2", "c1", "c2", "c1"],
        },
    )
    assert flow_employee_curator_user_ids(emp) == ["c2", "c1"]


def test_flow_employee_curator_user_ids_errors():
    human = User(user_id="u1", name="Human")
    with pytest.raises(ValueError):
        flow_employee_curator_user_ids(human)

    no_attr = User(user_id="flow_employee_f2", name="Emp", attributes={"kind": FLOW_EMPLOYEE_KIND})
    with pytest.raises(ValueError):
        flow_employee_curator_user_ids(no_attr)

    empty = User(
        user_id="flow_employee_f3",
        name="Emp",
        attributes={"kind": FLOW_EMPLOYEE_KIND, "curator_user_ids": ["  ", ""]},
    )
    with pytest.raises(ValueError):
        flow_employee_curator_user_ids(empty)


# --- Provisioning (двусторонний) ---


async def test_ensure_flow_employee_happy_two_sided(di, employee_company, unique_id):
    company_id, curator_id = employee_company
    flow_id = f"flow_{unique_id}"
    roles = ["member", "flow_operator"]

    user = await ensure_flow_employee(
        di.authz_service,
        flow_id=flow_id,
        company_id=company_id,
        name="AI Worker",
        roles=roles,
        curator_user_ids=[curator_id],
        avatar_url="https://example.com/a.png",
    )

    assert user.user_id == flow_employee_user_id(flow_id)
    assert user.status == UserStatus.ACTIVE
    assert is_flow_employee(user)
    assert require_flow_employee_flow_id(user) == flow_id
    assert flow_employee_curator_user_ids(user) == [curator_id]
    assert user.avatar_url == "https://example.com/a.png"
    assert user.companies[company_id] == roles

    stored = await User.get(user.user_id)
    assert stored is not None
    assert stored.companies[company_id] == roles

    company = await Company.get(company_id)
    assert company is not None
    assert set(company.members[user.user_id]) == set(roles)


async def test_ensure_flow_employee_idempotent_and_update(di, employee_company, unique_id):
    company_id, curator_id = employee_company
    flow_id = f"flow_{unique_id}"

    first = await ensure_flow_employee(
        di.authz_service,
        flow_id=flow_id,
        company_id=company_id,
        name="Worker",
        roles=["member"],
        curator_user_ids=[curator_id],
    )
    again = await ensure_flow_employee(
        di.authz_service,
        flow_id=flow_id,
        company_id=company_id,
        name="Worker Renamed",
        roles=["member"],
        curator_user_ids=[curator_id],
        avatar_url="https://example.com/new.png",
    )
    assert first.user_id == again.user_id
    assert again.name == "Worker Renamed"
    assert again.avatar_url == "https://example.com/new.png"

    company = await Company.get(company_id)
    assert company is not None
    # членство не дублируется
    assert company.members[again.user_id].count("member") == 1


async def test_ensure_flow_employee_edge_errors(di, employee_company, unique_id):
    company_id, curator_id = employee_company

    with pytest.raises(ValueError):
        await ensure_flow_employee(
            di.authz_service, flow_id="  ", company_id=company_id, name="X",
            roles=["member"], curator_user_ids=[curator_id],
        )
    with pytest.raises(ValueError):
        await ensure_flow_employee(
            di.authz_service, flow_id=f"f_{unique_id}", company_id="  ", name="X",
            roles=["member"], curator_user_ids=[curator_id],
        )
    with pytest.raises(ValueError):
        await ensure_flow_employee(
            di.authz_service, flow_id=f"f_{unique_id}", company_id=company_id, name="X",
            roles=["member"], curator_user_ids=[],
        )
    missing_company = f"missing_{uuid.uuid4().hex[:8]}"
    with pytest.raises(ValueError):
        await ensure_flow_employee(
            di.authz_service, flow_id=f"f_{unique_id}", company_id=missing_company, name="X",
            roles=["member"], curator_user_ids=[curator_id],
        )


async def test_deactivate_flow_employee(di, employee_company, unique_id):
    company_id, curator_id = employee_company
    flow_id = f"flow_{unique_id}"

    user = await ensure_flow_employee(
        di.authz_service, flow_id=flow_id, company_id=company_id, name="Worker",
        roles=["member"], curator_user_ids=[curator_id],
    )

    await deactivate_flow_employee(di.authz_service, flow_id=flow_id, company_id=company_id)

    stored = await User.get(user.user_id)
    assert stored is not None  # запись сохраняется для аудита
    assert stored.status == UserStatus.INACTIVE
    assert company_id not in stored.companies

    company = await Company.get(company_id)
    assert company is not None
    assert user.user_id not in company.members

    # повторная деактивация идемпотентна
    await deactivate_flow_employee(di.authz_service, flow_id=flow_id, company_id=company_id)


async def test_deactivate_missing_does_not_raise(di, employee_company, unique_id):
    company_id, _ = employee_company
    await deactivate_flow_employee(
        di.authz_service, flow_id=f"never_{unique_id}", company_id=company_id
    )


async def test_reactivate_flow_employee(di, employee_company, unique_id):
    company_id, curator_id = employee_company
    flow_id = f"flow_{unique_id}"

    await ensure_flow_employee(
        di.authz_service, flow_id=flow_id, company_id=company_id, name="Worker",
        roles=["member"], curator_user_ids=[curator_id],
    )
    await deactivate_flow_employee(di.authz_service, flow_id=flow_id, company_id=company_id)

    reactivated = await ensure_flow_employee(
        di.authz_service, flow_id=flow_id, company_id=company_id, name="Worker",
        roles=["member"], curator_user_ids=[curator_id],
    )
    assert reactivated.status == UserStatus.ACTIVE
    assert company_id in reactivated.companies

    company = await Company.get(company_id)
    assert company is not None
    assert reactivated.user_id in company.members
