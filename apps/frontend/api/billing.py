"""
API для биллинга, пополнения баланса и управления подпиской.
"""

from fastapi import APIRouter, HTTPException

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    BillingPlanChangeResponse,
    BillingSubscription,
    BillingUsage,
    ChangePlanRequest,
    PaymentHistoryResponse,
)
from core.clients.payment import PaymentProviderFactory
from core.context import require_context
from core.logging import get_logger
from core.models.billing_models import TariffPlan
from core.models.identity_models import Company, User
from core.models.payment_models import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    TransactionResponse,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])


def _require_billing_principal() -> tuple[User, Company]:
    context = require_context()
    company = context.active_company
    if company is None:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    return context.user, company


@router.get("/subscription", response_model=BillingSubscription)
async def get_subscription() -> BillingSubscription:
    _, company = _require_billing_principal()
    return BillingSubscription(
        plan=company.tariff_plan.value,
        balance=company.balance,
        monthly_budget=company.monthly_budget,
        current_month_spent=company.current_month_spent,
        billing_period_start=company.billing_period_start,
    )


@router.get("/usage", response_model=BillingUsage)
async def get_usage_stats(container: ContainerDep) -> BillingUsage:
    _, company = _require_billing_principal()
    stats = await container.billing_service.get_company_usage_stats(company.company_id)
    return BillingUsage.model_validate(stats)


@router.patch("/plan", response_model=BillingPlanChangeResponse)
async def change_plan(
    plan_request: ChangePlanRequest,
    container: ContainerDep,
) -> BillingPlanChangeResponse:
    user, company = _require_billing_principal()

    if "owner" not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Только владелец компании может менять тариф")

    try:
        tariff = TariffPlan(plan_request.plan)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый тариф. Допустимые: free, basic, premium, enterprise",
        ) from exc

    if tariff == company.tariff_plan:
        raise HTTPException(status_code=400, detail="Компания уже использует этот тариф")

    company.tariff_plan = tariff
    _ = await container.company_repository.set(company)

    logger.info("Тариф компании %s изменен на %s", company.company_id, tariff.value)

    return BillingPlanChangeResponse(
        success=True,
        plan=tariff.value,
        message=f"Тариф успешно изменен на {tariff.value}",
    )


@router.post("/topup", response_model=CreatePaymentResponse)
async def create_topup_payment(
    payment_request: CreatePaymentRequest,
    container: ContainerDep,
) -> CreatePaymentResponse:
    user, company = _require_billing_principal()

    user_roles = company.members.get(user.user_id, [])
    if "owner" not in user_roles and "admin" not in user_roles:
        raise HTTPException(
            status_code=403,
            detail="Только владелец или администратор может пополнять баланс",
        )

    provider = PaymentProviderFactory.get_default_provider()
    if provider is None:
        raise HTTPException(status_code=503, detail="Платежный провайдер не настроен")

    return await container.payment_service.create_payment(
        company=company,
        user=user,
        amount=payment_request.amount,
        provider=provider,
    )


@router.get("/history", response_model=PaymentHistoryResponse)
async def get_payment_history(
    container: ContainerDep,
) -> PaymentHistoryResponse:
    _, company = _require_billing_principal()

    transactions = await container.payment_service.get_company_transactions(
        company_id=company.company_id,
    )

    payments = [
        TransactionResponse(
            transaction_id=t.transaction_id,
            company_id=t.company_id,
            amount=t.amount,
            status=t.status,
            payment_provider=t.payment_provider,
            external_payment_id=t.external_payment_id,
            created_at=t.created_at,
            completed_at=t.completed_at,
            metadata=t.metadata,
        )
        for t in transactions
    ]

    return PaymentHistoryResponse(payments=payments)
