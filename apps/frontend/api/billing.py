"""
API для биллинга, пополнения баланса и управления подпиской.
"""

from fastapi import APIRouter, HTTPException, Request

from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import BillingSubscription, BillingUsage, ChangePlanRequest
from core.clients.payment import PaymentProviderFactory
from core.logging import get_logger
from core.models.billing_models import TariffPlan
from core.models.payment_models import CreatePaymentRequest, TransactionResponse

logger = get_logger(__name__)
router = APIRouter(prefix="/api/billing", tags=["billing"])

@router.get("/subscription", response_model=BillingSubscription)
async def get_subscription(request: Request, container: ContainerDep):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    company = request.state.company
    return BillingSubscription(
        plan=company.tariff_plan.value,
        balance=company.balance,
        monthly_budget=company.monthly_budget,
        current_month_spent=company.current_month_spent,
        billing_period_start=company.billing_period_start,
    )

@router.get("/usage", response_model=BillingUsage)
async def get_usage_stats(request: Request, container: ContainerDep):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    company = request.state.company

    from core.context import set_context
    if hasattr(request.state, "context"):
        set_context(request.state.context)

    stats = await container.billing_service.get_company_usage_stats(company.company_id)
    return BillingUsage(**stats)

@router.patch("/plan")
async def change_plan(
    plan_request: ChangePlanRequest,
    request: Request,
    container: ContainerDep,
):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    user = request.state.user
    company = request.state.company

    if "owner" not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Только владелец компании может менять тариф")

    try:
        tariff = TariffPlan(plan_request.plan)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Недопустимый тариф. Допустимые: free, basic, premium, enterprise",
        )

    if tariff == company.tariff_plan:
        raise HTTPException(status_code=400, detail="Компания уже использует этот тариф")

    company.tariff_plan = tariff
    await container.company_repository.set(company)

    logger.info("Тариф компании %s изменен на %s", company.company_id, tariff.value)

    return {
        "success": True,
        "plan": tariff.value,
        "message": f"Тариф успешно изменен на {tariff.value}",
    }

@router.post("/topup")
async def create_topup_payment(
    payment_request: CreatePaymentRequest,
    request: Request,
    container: ContainerDep,
):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    user = request.state.user
    company = request.state.company

    user_roles = company.members.get(user.user_id, [])
    if "owner" not in user_roles and "admin" not in user_roles:
        raise HTTPException(status_code=403, detail="Только владелец или администратор может пополнять баланс")

    provider = PaymentProviderFactory.get_default_provider()
    if not provider:
        raise HTTPException(status_code=503, detail="Платежный провайдер не настроен")

    result = await container.payment_service.create_payment(
        company=company,
        user=user,
        amount=payment_request.amount,
        provider=provider,
    )

    return {
        "success": True,
        "payment_id": result["transaction_id"],
        "payment_url": result["payment_url"],
        "amount": result["amount"],
    }

@router.get("/history")
async def get_payment_history(
    request: Request,
    container: ContainerDep,
):
    if not hasattr(request.state, "user") or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    if not hasattr(request.state, "company") or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")

    company = request.state.company

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

    return {"payments": [p.model_dump(mode="json") for p in payments]}
