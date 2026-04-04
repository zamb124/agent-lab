"""
API для биллинга и управления подпиской
"""
import logging
from fastapi import APIRouter, HTTPException, Request
from apps.frontend.dependencies import ContainerDep
from apps.frontend.models import (
    BillingSubscription,
    BillingUsage,
    TopUpRequest,
    ChangePlanRequest
)
from core.models.billing_models import TariffPlan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/subscription", response_model=BillingSubscription)
async def get_subscription(request: Request, container: ContainerDep):
    """
    Получить информацию о текущей подписке
    
    Returns:
        Информация о тарифе, балансе, лимитах
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    company = request.state.company
    
    return BillingSubscription(
        plan=company.tariff_plan.value,
        balance=company.balance,
        monthly_budget=company.monthly_budget,
        current_month_spent=company.current_month_spent,
        billing_period_start=company.billing_period_start
    )


@router.get("/usage", response_model=BillingUsage)
async def get_usage_stats(request: Request, container: ContainerDep):
    """
    Получить статистику использования ресурсов
    
    Returns:
        Детальная статистика использования за текущий месяц
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    company = request.state.company

    from core.context import set_context

    if hasattr(request.state, 'context'):
        set_context(request.state.context)

    stats = await container.billing_service.get_company_usage_stats(company.company_id)
    return BillingUsage(**stats)


@router.post("/topup")
async def create_topup_payment(
    topup: TopUpRequest,
    request: Request,
    container: ContainerDep
):
    """
    Создать платеж на пополнение баланса
    
    Args:
        topup: Данные платежа (сумма, метод)
    
    Returns:
        URL для оплаты или информация о платеже
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []) and \
       'admin' not in company.members.get(user.user_id, []):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    
    # TODO: Интеграция с платежной системой (Stripe, YooKassa)
    logger.info(
        f"Создан платеж на пополнение: {topup.amount} RUB "
        f"для компании {company.company_id}"
    )
    
    return {
        "success": True,
        "payment_id": "mock_payment_id",
        "amount": topup.amount,
        "status": "pending",
        "payment_url": "https://payment.mock/pay",
        "message": "Платежная интеграция в разработке. Mock данные."
    }


@router.patch("/plan")
async def change_plan(
    plan_request: ChangePlanRequest,
    request: Request,
    container: ContainerDep
):
    """
    Сменить тарифный план
    
    Args:
        plan_request: Новый тарифный план
    
    Returns:
        Информация об обновленном тарифе
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    user = request.state.user
    company = request.state.company
    
    if 'owner' not in company.members.get(user.user_id, []):
        raise HTTPException(
            status_code=403,
            detail="Только владелец компании может менять тариф"
        )
    
    try:
        new_plan = TariffPlan(plan_request.plan)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Недопустимый тариф. Допустимые: free, basic, premium, enterprise"
        )
    
    if new_plan == company.tariff_plan:
        raise HTTPException(
            status_code=400,
            detail="Компания уже использует этот тариф"
        )
    
    company.tariff_plan = new_plan
    company_repo = container.company_repository
    await company_repo.set(company)
    
    logger.info(f"Тариф компании {company.company_id} изменен на {new_plan.value}")
    
    return {
        "success": True,
        "plan": new_plan.value,
        "message": f"Тариф успешно изменен на {new_plan.value}"
    }


@router.get("/history")
async def get_payment_history(request: Request, container: ContainerDep):
    """
    Получить историю платежей
    
    Returns:
        Список платежей компании
    """
    if not hasattr(request.state, 'user') or not request.state.user:
        raise HTTPException(status_code=401, detail="Необходима авторизация")
    
    if not hasattr(request.state, 'company') or not request.state.company:
        raise HTTPException(status_code=400, detail="Компания не выбрана")
    
    # TODO: Реализовать репозиторий платежей
    logger.info("Запрошена история платежей (mock)")
    
    return {
        "payments": [],
        "message": "История платежей в разработке"
    }

