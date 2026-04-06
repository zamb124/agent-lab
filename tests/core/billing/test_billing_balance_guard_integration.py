"""
Pre-flight require_balance_for_billable_operation: нулевой баланс, exempt system.
"""

from __future__ import annotations

import pytest

from core.billing.exceptions import BillingBalanceBlockedError
from core.billing.service import BALANCE_BLOCK_OPERATION_LLM, BillingService
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.identity_models import Company


def _minimal_base_prices() -> dict:
    return {"llm": {"*": 1.0}}


@pytest.mark.asyncio
async def test_require_balance_zero_blocks(
    frontend_container, unique_id, system_user_id, monkeypatch: pytest.MonkeyPatch
) -> None:
    cid = f"co_zero_bal_{unique_id}"
    company = Company(
        company_id=cid,
        name="Zero balance",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=0.0,
    )
    await frontend_container.company_repository.set(company)
    notify_calls: list[tuple[str, object]] = []

    async def _capture_notify(user_id: str, notification: object) -> None:
        notify_calls.append((user_id, notification))

    monkeypatch.setattr("core.billing.service.notify_user", _capture_notify)

    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        resource_base_prices=_minimal_base_prices(),
        shared_storage=None,
        balance_enforcement_enabled=True,
        balance_enforcement_exempt_company_ids=[],
    )
    with pytest.raises(BillingBalanceBlockedError):
        await billing.require_balance_for_billable_operation(
            cid,
            system_user_id,
            operation_code=BALANCE_BLOCK_OPERATION_LLM,
            notification_service="frontend",
        )
    assert len(notify_calls) == 1
    assert notify_calls[0][0] == system_user_id


@pytest.mark.asyncio
async def test_require_balance_system_exempt(frontend_container) -> None:
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        resource_base_prices=_minimal_base_prices(),
        shared_storage=None,
        balance_enforcement_enabled=True,
        balance_enforcement_exempt_company_ids=[SYSTEM_COMPANY_ID],
    )
    await billing.require_balance_for_billable_operation(
        SYSTEM_COMPANY_ID,
        "any_user_for_notify",
        operation_code=BALANCE_BLOCK_OPERATION_LLM,
        notification_service="frontend",
    )


@pytest.mark.asyncio
async def test_require_balance_disabled_noop(frontend_container, unique_id, system_user_id) -> None:
    cid = f"co_off_{unique_id}"
    company = Company(
        company_id=cid,
        name="Off",
        owner_user_id=system_user_id,
        members={system_user_id: ["owner"]},
        balance=0.0,
    )
    await frontend_container.company_repository.set(company)
    billing = BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        resource_base_prices=_minimal_base_prices(),
        shared_storage=None,
        balance_enforcement_enabled=False,
        balance_enforcement_exempt_company_ids=[],
    )
    await billing.require_balance_for_billable_operation(
        cid,
        system_user_id,
        operation_code=BALANCE_BLOCK_OPERATION_LLM,
        notification_service="frontend",
    )
