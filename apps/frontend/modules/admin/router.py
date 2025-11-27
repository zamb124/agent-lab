"""
Роутер модуля Admin - управление компаниями (только для system админов)
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from apps.frontend.core.template_loader import get_templates
from core.context import get_context
from apps.frontend.container import get_frontend_container
from core.models.billing_models import TariffPlan

router = APIRouter(prefix="/frontend/admin", tags=["admin-pages"])
templates = get_templates()


def is_system_admin(request: Request) -> bool:
    """Проверяет что пользователь - администратор из компании system"""
    context = get_context()
    if not context or not context.user:
        return False
    
    user = context.user
    
    # Проверяем что у пользователя есть роль admin в компании system
    if "system" in user.companies:
        system_roles = user.companies["system"]
        if "admin" in system_roles:
            return True
    
    return False


@router.get("/companies", response_class=HTMLResponse)
async def admin_companies(request: Request):
    """Страница управления компаниями (только для system админов)"""
    
    if not is_system_admin(request):
        raise HTTPException(status_code=403, detail="Доступ запрещен. Требуется роль администратора системы.")
    
    context = get_context()
    user = context.user if context else None
    
    container = get_frontend_container()
    company_repo = container.company_repository
    
    companies = await company_repo.list_all(limit=1000)
    
    # Сортируем по дате создания
    companies.sort(key=lambda c: c.created_at, reverse=True)
    
    return templates.TemplateResponse(
        "admin_companies.html",
        {
            "request": request,
            "user": user,
            "companies": companies,
            "tariff_plans": TariffPlan,
        }
    )


@router.post("/api/companies/{company_id}/balance", response_class=JSONResponse)
async def update_company_balance(request: Request, company_id: str):
    """Пополнить баланс компании"""
    
    if not is_system_admin(request):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    data = await request.json()
    amount = data.get("amount", 0)
    
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Сумма пополнения должна быть больше 0")
    
    container = get_frontend_container()
    company_repo = container.company_repository
    
    company = await company_repo.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    
    old_balance = company.balance
    company.balance += float(amount)
    
    await company_repo.set(company)
    
    return {
        "success": True,
        "message": f"Баланс компании {company.name} пополнен на {amount}₽",
        "company_id": company_id,
        "old_balance": old_balance,
        "new_balance": company.balance
    }


@router.post("/api/companies/{company_id}/monthly-limit", response_class=JSONResponse)
async def update_company_monthly_limit(request: Request, company_id: str):
    """Установить месячный лимит компании"""
    
    if not is_system_admin(request):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    data = await request.json()
    new_limit = data.get("limit", 0)
    
    if new_limit < 0:
        raise HTTPException(status_code=400, detail="Лимит не может быть отрицательным")
    
    container = get_frontend_container()
    company_repo = container.company_repository
    
    company = await company_repo.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    
    company.monthly_budget = float(new_limit)
    
    await company_repo.set(company)
    
    return {
        "success": True,
        "message": f"Месячный лимит компании {company.name} установлен: {new_limit}₽",
        "company_id": company_id,
        "new_limit": new_limit
    }


@router.post("/api/companies/{company_id}/tariff", response_class=JSONResponse)
async def update_company_tariff(request: Request, company_id: str):
    """Изменить тариф компании"""
    
    if not is_system_admin(request):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    data = await request.json()
    new_tariff = data.get("tariff")
    
    try:
        tariff_plan_enum = TariffPlan(new_tariff)
    except ValueError:
        raise HTTPException(status_code=400, detail="Неверный тарифный план")
    
    container = get_frontend_container()
    company_repo = container.company_repository
    
    company = await company_repo.get(company_id)
    if not company:
        raise HTTPException(status_code=404, detail="Компания не найдена")
    
    company.tariff_plan = tariff_plan_enum
    
    await company_repo.set(company)
    
    return {
        "success": True,
        "message": f"Тариф компании {company.name} изменен на {new_tariff}",
        "company_id": company_id,
        "new_tariff": new_tariff
    }


@router.post("/api/companies/{company_id}/reset-billing", response_class=JSONResponse)
async def reset_company_billing(request: Request, company_id: str):
    """Сбросить месячный биллинг компании"""
    
    if not is_system_admin(request):
        raise HTTPException(status_code=403, detail="Доступ запрещен")
    
    agents_container = request.app.state.agents_container
    if not agents_container:
        raise HTTPException(status_code=500, detail="AgentsContainer не инициализирован")
    
    billing_service = agents_container.billing_service
    await billing_service.reset_monthly_billing(company_id)
    
    return {
        "success": True,
        "message": f"Месячный биллинг компании {company_id} сброшен"
    }

