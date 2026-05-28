"""Интеграция: ``BillingService.company_may_incur_billable_operation_charge``."""

from __future__ import annotations

import pytest

from core.billing.service import BillingService
from core.identity.system_bootstrap import SYSTEM_COMPANY_ID
from core.models.billing_models import DEFAULT_TARIFF_PRICES
from core.models.identity_models import Company


def _minimal_base_prices() -> dict[str, dict[str, float]]:
    return {"llm": {"*": 1.0}}


def _make_billing(
    frontend_container,
    *,
    enforcement: bool = True,
    exempt: list[str] | None = None,
) -> BillingService:
    return BillingService(
        frontend_container.company_repository,
        frontend_container.user_repository,
        frontend_container.usage_repository,
        tariff_prices=DEFAULT_TARIFF_PRICES,
        resource_base_prices=_minimal_base_prices(),
        shared_storage=None,
        balance_enforcement_enabled=enforcement,
        balance_enforcement_exempt_company_ids=exempt or [],
    )


@pytest.mark.asyncio
async def test_empty_id_raises(frontend_container) -> None:
    billing = _make_billing(frontend_container)
    with pytest.raises(ValueError, match="company_id обязателен"):
        await billing.company_may_incur_billable_operation_charge("  ")


@pytest.mark.asyncio
async def test_enforcement_off_allows_zero_balance(
    frontend_container, unique_id, system_user_id
) -> None:
    cid = f"co_emb_off_{unique_id}"
    await frontend_container.company_repository.set(
        Company(
            company_id=cid,
            name="EnforcementOff",
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=0.0,
        )
    )
    billing = _make_billing(frontend_container, enforcement=False)
    assert await billing.company_may_incur_billable_operation_charge(cid) is True


@pytest.mark.asyncio
async def test_exempt_company_allowed(frontend_container) -> None:
    billing = _make_billing(frontend_container, exempt=[SYSTEM_COMPANY_ID])
    assert await billing.company_may_incur_billable_operation_charge(SYSTEM_COMPANY_ID) is True


@pytest.mark.asyncio
async def test_missing_company_returns_false(frontend_container, unique_id) -> None:
    billing = _make_billing(frontend_container)
    assert await billing.company_may_incur_billable_operation_charge(f"nosuch_{unique_id}") is False


@pytest.mark.asyncio
async def test_zero_balance_returns_false(
    frontend_container, unique_id, system_user_id
) -> None:
    cid = f"co_emb_zero_{unique_id}"
    await frontend_container.company_repository.set(
        Company(
            company_id=cid,
            name="Zero",
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=0.0,
        )
    )
    billing = _make_billing(frontend_container)
    assert await billing.company_may_incur_billable_operation_charge(cid) is False


@pytest.mark.asyncio
async def test_positive_balance_returns_true(
    frontend_container, unique_id, system_user_id
) -> None:
    cid = f"co_emb_pos_{unique_id}"
    await frontend_container.company_repository.set(
        Company(
            company_id=cid,
            name="Pos",
            owner_user_id=system_user_id,
            members={system_user_id: ["owner"]},
            balance=5.0,
        )
    )
    billing = _make_billing(frontend_container)
    assert await billing.company_may_incur_billable_operation_charge(cid) is True
