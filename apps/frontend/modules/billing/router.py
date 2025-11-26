"""
Роутер модуля Billing - управление биллингом и тарификацией
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.plugin_loader import get_plugins_for_template
from core.context import get_context
from core.billing import BillingService
from core.payments import PaymentService
from core.models.billing_models import TariffPlan, TARIFF_PRICES

router = APIRouter(prefix="/frontend/billing", tags=["billing-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def billing_index(request: Request):
    """Главная страница биллинга"""
    
    context = get_context()
    user = context.user if context else None
    company = context.active_company if context else None
    
    if not user or not company:
        return templates.TemplateResponse(
            "billing.html",
            {
                "request": request,
                "error": "Не удалось загрузить данные пользователя или компании"
            }
        )
    
    billing_service = BillingService()
    payment_service = PaymentService()
    
    stats = await billing_service.get_company_usage_stats(company.company_id)
    
    # Получаем историю платежей (последние 10)
    payment_history = await payment_service.get_company_transactions(
        company_id=company.company_id,
        limit=10,
        offset=0
    )
    
    tariff_prices = TARIFF_PRICES.get(company.tariff_plan, {})
    
    budget_percent = 0
    if company.monthly_budget > 0:
        budget_percent = min(100, (company.current_month_spent / company.monthly_budget) * 100)
    
    plugin_data = get_plugins_for_template(request)
    
    return templates.TemplateResponse(
        "billing.html",
        {
            "request": request,
            "user": user,
            "company": company,
            "stats": stats,
            "tariff_prices": tariff_prices,
            "budget_percent": budget_percent,
            "tariff_plans": TariffPlan,
            "payment_history": payment_history,
            **plugin_data
        }
    )


@router.get("/api/stats", response_class=JSONResponse)
async def billing_stats(request: Request):
    """API для получения статистики биллинга"""
    
    context = get_context()
    company = context.active_company if context else None
    
    if not company:
        return JSONResponse(
            status_code=403,
            content={"error": "No active company"}
        )
    
    billing_service = BillingService()
    stats = await billing_service.get_company_usage_stats(company.company_id)
    
    return {
        "company_id": company.company_id,
        "tariff_plan": company.tariff_plan,
        "monthly_budget": company.monthly_budget,
        "current_month_spent": company.current_month_spent,
        "stats": stats
    }


@router.post("/api/payment", response_class=JSONResponse)
async def initiate_payment(request: Request):
    """Инициализация платежа (заглушка для будущей интеграции)"""
    
    data = await request.json()
    amount = data.get("amount", 0)
    
    # Пока возвращаем заглушку
    return {
        "success": True,
        "message": "Функция оплаты будет доступна в следующих версиях",
        "payment_url": "#",
        "amount": amount
    }
