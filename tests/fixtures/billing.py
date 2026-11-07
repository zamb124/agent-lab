"""BillingService для unit/integration тестов без process-global."""

from __future__ import annotations

from core.billing.service import BillingService
from core.models.billing_models import DEFAULT_TARIFF_PRICES


def make_test_billing_service(
    *,
    balance_enforcement_enabled: bool = False,
) -> BillingService:
    """Минимальный BillingService для конструкторов LLM/embedding/RAG в тестах."""
    return BillingService(
        tariff_prices=DEFAULT_TARIFF_PRICES,
        resource_base_prices={"llm": {"*": 1.0}, "embedding": {"*": 1.0}},
        shared_storage=None,
        balance_enforcement_enabled=balance_enforcement_enabled,
        balance_enforcement_exempt_company_ids=[],
    )
