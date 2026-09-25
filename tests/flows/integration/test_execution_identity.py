"""Подмена identity исполнения flow-сотрудника (`services/execution_identity.py`).

Реальные репозитории; initiator-Context через `build_job_context`. Единственный
мок — отсутствует (LLM не задействован).
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from apps.flows.src.models.flow_config import FlowConfig, FlowEmployeeConfig
from apps.flows.src.services.execution_identity import resolve_execution_context
from core.context.job_context import build_job_context
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import Company, User
from core.utils.tokens import get_token_service
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def initiator_and_company(di, unique_id):
    company_id = f"exec_co_{unique_id}"
    initiator_id = f"initiator_{unique_id}"
    company = make_test_company(
        company_id=company_id,
        name="Exec Co",
        owner_user_id=initiator_id,
        members={initiator_id: ["owner", "admin"]},
    )
    await Company.set(company)
    initiator = User(
        user_id=initiator_id,
        name="Initiator",
        companies={company_id: ["owner", "admin"]},
        active_company_id=company_id,
    )
    await User.set(initiator)
    ctx = build_job_context(
        company=company,
        user=initiator,
        host="test",
        trace_id=f"trace_{unique_id}",
        session_id=f"sess_{unique_id}",
        channel="test",
    )
    yield ctx, company, company_id, initiator_id
    await User.delete_by_id(initiator_id)
    await Company.delete_by_id(company_id)


def _flow(flow_id: str, *, enabled: bool, curator: str = "c1") -> FlowConfig:
    return FlowConfig(
        flow_id=flow_id,
        name="Flow",
        entry="main",
        nodes={"main": {"node_type": "llm_node"}},
        employee=FlowEmployeeConfig(
            enabled=enabled,
            roles=["member"] if enabled else [],
            curator_user_ids=[curator] if enabled else [],
        ),
    )


async def test_regular_flow_returns_initiator(di, initiator_and_company, unique_id):
    ctx, _company, _company_id, initiator_id = initiator_and_company
    flow = _flow(f"regular_{unique_id}", enabled=False)

    resolved = await resolve_execution_context(di, flow_config=flow, initiator_context=ctx)

    assert resolved.is_employee is False
    assert resolved.initiator_user_id == initiator_id
    assert resolved.context.user.user_id == initiator_id


async def test_employee_flow_switches_identity(di, initiator_and_company, unique_id):
    ctx, _company, company_id, initiator_id = initiator_and_company
    flow_id = f"emp_exec_{unique_id}"
    await ensure_flow_employee(
        di,
        flow_id=flow_id,
        company_id=company_id,
        name="AI Worker",
        roles=["member", "flow_operator"],
        curator_user_ids=[initiator_id],
    )
    flow = _flow(flow_id, enabled=True, curator=initiator_id)

    resolved = await resolve_execution_context(di, flow_config=flow, initiator_context=ctx)

    assert resolved.is_employee is True
    assert resolved.initiator_user_id == initiator_id
    assert resolved.context.user.user_id == flow_employee_user_id(flow_id)

    token_data = get_token_service().validate_token(resolved.context.auth_token)
    assert token_data is not None
    assert token_data.user_id == flow_employee_user_id(flow_id)
    assert token_data.company_id == company_id

    meta = resolved.context.metadata
    assert meta["context_type"] == "flow_employee"
    assert meta["initiator_user_id"] == initiator_id
    assert "member" in meta["grps"] and "flow_operator" in meta["grps"]
    # унаследовано от инициатора
    assert resolved.context.active_namespace == ctx.active_namespace
    assert resolved.context.language == ctx.language


async def test_employee_not_provisioned_raises(di, initiator_and_company, unique_id):
    ctx, _company, _company_id, _initiator_id = initiator_and_company
    flow = _flow(f"missing_emp_{unique_id}", enabled=True)
    with pytest.raises(ValueError):
        await resolve_execution_context(di, flow_config=flow, initiator_context=ctx)


async def test_employee_user_not_employee_raises(di, initiator_and_company, unique_id):
    ctx, _company, company_id, _initiator_id = initiator_and_company
    flow_id = f"fake_emp_{unique_id}"
    # создаём обычного user с id сотрудника, но без employee-атрибутов
    fake = User(
        user_id=flow_employee_user_id(flow_id),
        name="Fake",
        companies={company_id: ["member"]},
        active_company_id=company_id,
    )
    await User.set(fake)
    flow = _flow(flow_id, enabled=True)
    with pytest.raises(ValueError):
        await resolve_execution_context(di, flow_config=flow, initiator_context=ctx)
    await User.delete_by_id(fake.user_id)


async def test_employee_requires_active_company(di, initiator_and_company, unique_id):
    ctx, _company, _company_id, _initiator_id = initiator_and_company
    flow = _flow(f"no_co_{unique_id}", enabled=True)
    ctx_no_company = ctx.model_copy(update={"active_company": None})
    with pytest.raises(ValueError, match="active company"):
        await resolve_execution_context(
            di,
            flow_config=flow,
            initiator_context=ctx_no_company,
        )


async def test_employee_not_member_raises(di, initiator_and_company, unique_id):
    ctx, _company, company_id, initiator_id = initiator_and_company
    flow_id = f"nonmember_emp_{unique_id}"
    await ensure_flow_employee(
        di,
        flow_id=flow_id,
        company_id=company_id,
        name="AI Worker",
        roles=["member"],
        curator_user_ids=[initiator_id],
    )
    # снимаем членство сотрудника в компании
    emp = await User.get(flow_employee_user_id(flow_id))
    assert emp is not None
    emp.companies.pop(company_id, None)
    await User.set(emp)

    flow = _flow(flow_id, enabled=True)
    with pytest.raises(ValueError):
        await resolve_execution_context(di, flow_config=flow, initiator_context=ctx)
