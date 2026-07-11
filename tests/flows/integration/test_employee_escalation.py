"""Эскалации: `_resolve_escalation_targets` маршрутизирует уведомления.

Человек — самому себе; фоновый flow-сотрудник — его кураторам; безопасный fallback.
Реальные репозитории, без моков.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from apps.flows.src.tasks.scheduled_tasks import _resolve_escalation_targets
from core.identity.flow_employee import ensure_flow_employee, flow_employee_user_id
from core.models.identity_models import User
from tests.fixtures.ai_provider_defaults import make_test_company

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def esc_company(container, unique_id):
    company_id = f"esc_co_{unique_id}"
    company = make_test_company(company_id=company_id, name="Esc Co", members={})
    await container.company_repository.set(company)
    yield company_id
    await container.company_repository.delete(company_id)


async def test_human_target_returns_self(container, unique_id):
    targets = await _resolve_escalation_targets(container, f"human_{unique_id}")
    assert targets == [f"human_{unique_id}"]


async def test_employee_target_returns_curators(container, esc_company, unique_id):
    flow_id = f"esc_flow_{unique_id}"
    curators = [f"cur1_{unique_id}", f"cur2_{unique_id}"]
    await ensure_flow_employee(
        container,
        flow_id=flow_id,
        company_id=esc_company,
        name="AI Worker",
        roles=["member"],
        curator_user_ids=curators,
    )
    emp_id = flow_employee_user_id(flow_id)
    try:
        targets = await _resolve_escalation_targets(container, emp_id)
        assert targets == curators
    finally:
        await container.user_repository.delete(emp_id)


async def test_employee_prefix_but_missing_user_fallback(container, unique_id):
    ghost = flow_employee_user_id(f"ghost_{unique_id}")
    targets = await _resolve_escalation_targets(container, ghost)
    assert targets == [ghost]


async def test_employee_prefix_but_not_employee_fallback(container, unique_id):
    fake_id = flow_employee_user_id(f"fake_{unique_id}")
    fake = User(user_id=fake_id, name="Fake")  # без employee-атрибутов
    await container.user_repository.set(fake)
    try:
        targets = await _resolve_escalation_targets(container, fake_id)
        assert targets == [fake_id]
    finally:
        await container.user_repository.delete(fake_id)
