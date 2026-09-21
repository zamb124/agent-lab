"""Команды биллинга компании: подписка, usage, тариф, пополнение, история платежей."""

from __future__ import annotations

from pydantic import Field

from apps.frontend.container import FrontendContainer
from apps.frontend.models import (
    BillingPlanChangeResponse,
    BillingSubscription,
    BillingUsage,
    ChangePlanRequest,
)
from core.authz.errors import AuthzDenied
from core.authz.models import AuthzObject
from core.authz.types import AuthzRelation
from core.clients.payment import PaymentProviderFactory
from core.context import require_active_company
from core.errors.boundary import PlatformUnavailableError
from core.logging import get_logger
from core.models import StrictBaseModel
from core.models.billing_models import TariffPlan
from core.models.identity_models import User
from core.models.payment_models import CreatePaymentResponse, TransactionResponse
from core.pagination import ListResponse
from core.request_scope import require_company, require_company_admin
from core.websocket import EmptyPayload, raise_forbidden, raise_invalid

logger = get_logger(__name__)


class BillingTopupPayload(StrictBaseModel):
    """Сумма пополнения и origin браузера для redirect URL платёжного провайдера."""

    amount: float = Field(ge=100.0, le=1000000.0)
    public_host: str = Field(min_length=1)


async def op_billing_subscription(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> BillingSubscription:
    _ = payload, user, container
    _ = require_company()
    company = require_active_company()
    return BillingSubscription(
        plan=company.tariff_plan.value,
        balance=company.balance,
        monthly_budget=company.monthly_budget,
        current_month_spent=company.current_month_spent,
        billing_period_start=company.billing_period_start,
    )


async def op_billing_usage(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> BillingUsage:
    _ = payload, user
    scope = require_company()
    stats = await container.billing_service.get_company_usage_stats(scope.company_id)
    return BillingUsage.model_validate(stats)


async def op_billing_plan_change(
    payload: ChangePlanRequest, *, user: User, container: FrontendContainer
) -> BillingPlanChangeResponse:
    """Смена тарифа — только owner компании (FGA relation `owner`)."""
    scope = require_company()
    company = require_active_company()
    try:
        await container.authz_service.require_relation(
            AuthzRelation.OWNER, AuthzObject.company(scope.company_id), user_id=user.user_id
        )
    except AuthzDenied as exc:
        raise_forbidden(exc)
    try:
        tariff = TariffPlan(payload.plan)
    except ValueError:
        raise_invalid(ValueError("invalid tariff. allowed: free, basic, premium, enterprise"))
    if tariff == company.tariff_plan:
        raise_invalid(ValueError("company already uses this tariff"))
    company.tariff_plan = tariff
    _ = await container.company_repository.set(company)
    logger.info("billing.plan_changed", company_id=company.company_id, plan=tariff.value)
    return BillingPlanChangeResponse(success=True, plan=tariff.value, message=f"Тариф успешно изменен на {tariff.value}")


async def op_billing_topup(
    payload: BillingTopupPayload, *, user: User, container: FrontendContainer
) -> CreatePaymentResponse:
    _ = await require_company_admin(container.authz_service)
    company = require_active_company()
    provider = PaymentProviderFactory.get_default_provider()
    if provider is None:
        raise PlatformUnavailableError("Payment provider is not configured", error_code='unavailable')
    return await container.payment_service.create_payment(
        company=company, user=user, amount=payload.amount, provider=provider, host=payload.public_host.strip()
    )


async def op_billing_payment_history(
    payload: EmptyPayload, *, user: User, container: FrontendContainer
) -> ListResponse[TransactionResponse]:
    _ = payload, user
    scope = require_company()
    transactions = await container.payment_service.get_company_transactions(company_id=scope.company_id)
    return ListResponse[TransactionResponse](
        items=[
            TransactionResponse(
                transaction_id=transaction.transaction_id,
                company_id=transaction.company_id,
                amount=transaction.amount,
                status=transaction.status,
                payment_provider=transaction.payment_provider,
                external_payment_id=transaction.external_payment_id,
                created_at=transaction.created_at,
                completed_at=transaction.completed_at,
                metadata=transaction.metadata,
            )
            for transaction in transactions
        ]
    )
