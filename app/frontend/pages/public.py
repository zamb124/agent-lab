"""
Публичные страницы (landing page и т.д.)
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime
from app.frontend.core.template_loader import get_templates
from app.core.config import settings
from app.db.repositories import Storage
from app.models.core_models import FlowConfig

router = APIRouter(tags=["public-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Главная страница - лендинг Agents Lab"""
    from app.frontend.core.plugin_loader import get_plugins_for_template
    
    context = getattr(request.state, 'context', None)
    is_authenticated = (
        context and 
        context.user and 
        context.user.user_id != "anonymous"
    )
    
    plugins_data = get_plugins_for_template()
    
    return templates.TemplateResponse(
        "landing.html", 
        {
            "request": request, 
            "is_authenticated": is_authenticated,
            "dashboard_widgets": plugins_data.get("dashboard_widgets", [])
        }
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(
    request: Request,
    flow_id: Optional[str] = Query(None, description="ID flow для специфичной политики"),
    lang: Optional[str] = Query(None, description="Язык (ru/en)")
):
    """Страница политики конфиденциальности"""
    
    # Определяем язык из параметра или из контекста
    if lang:
        if lang not in ["ru", "en"]:
            lang = "ru"
    else:
        # Берем из контекста если есть
        lang = getattr(request.state, 'language', 'ru')
    
    # Устанавливаем язык в request.state для работы t()
    request.state.language = lang
    
    company_name = settings.legal.company_name_ru if lang == "ru" else settings.legal.company_name_en
    legal_form = settings.legal.legal_form_ru if lang == "ru" else settings.legal.legal_form_en
    legal_address = settings.legal.legal_address_ru if lang == "ru" else settings.legal.legal_address_en
    
    flow_info = None
    if flow_id:
        storage = Storage()
        flow_data = await storage.get(flow_id, force_global=True)
        if flow_data:
            flow_config = FlowConfig.model_validate_json(flow_data)
            flow_info = {
                "name": flow_config.name,
                "description": flow_config.description
            }
    
    return templates.TemplateResponse(
        "privacy.html",
        {
            "request": request,
            "lang": lang,
            "company_name": company_name,
            "legal_form": legal_form,
            "legal_address": legal_address or "",
            "inn": settings.legal.inn or "",
            "ogrn": settings.legal.ogrn or "",
            "contact_email": settings.legal.contact_email,
            "support_email": settings.legal.support_email,
            "dpo_email": settings.legal.dpo_email,
            "phone": settings.legal.phone or "",
            "site_url": f"https://{settings.server.domain}",
            "domain": settings.server.domain,
            "min_age": settings.legal.min_age,
            "retention_logs": settings.legal.retention_logs,
            "retention_messages": settings.legal.retention_messages,
            "retention_accounts": settings.legal.retention_accounts,
            "cloud_provider": settings.legal.cloud_provider,
            "cloud_region": settings.legal.cloud_region,
            "analytics_tools": settings.legal.analytics_tools,
            "billing_provider": settings.legal.billing_provider or "N/A",
            "current_date": datetime.now().strftime("%d.%m.%Y" if lang == "ru" else "%B %d, %Y"),
            "flow_info": flow_info
        }
    )

