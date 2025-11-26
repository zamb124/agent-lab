"""
Публичные страницы (landing page и т.д.)
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime
from apps.frontend.core.template_loader import get_templates
from core.config import settings

from apps.agents.models import FlowConfig
from core.models.i18n_models import Language
from core.context import get_context
from core.i18n import get_translation_manager
from apps.frontend.container import get_frontend_container

router = APIRouter(tags=["public-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Главная страница - лендинг Agents Lab"""
    from apps.frontend.core.plugin_loader import get_plugins_for_template
    
    # Определяем язык из cookie ПЕРЕД получением контекста
    lang_cookie = request.cookies.get("language", "ru")
    try:
        active_lang_enum = Language(lang_cookie)
    except ValueError:
        active_lang_enum = Language.RU
        
    # Устанавливаем язык в request.state, чтобы контекст его подхватил
    request.state.language = active_lang_enum
    
    context = getattr(request.state, 'context', None)
    
    # Дополнительно проверяем и устанавливаем язык в контексте, если он уже создан
    if context:
        context.language = active_lang_enum
        
    is_authenticated = (
        context and 
        context.user and 
        context.user.user_id != "anonymous"
    )
    
    plugins_data = get_plugins_for_template(request)
    
    # Получаем менеджер переводов и данные для шаблона
    manager = get_translation_manager()
    active_language = active_lang_enum.value
    
    ru_translations = manager.get_translations(Language.RU)
    supported_languages = {}
    for lang in Language:
        lang_key = f"languages.{lang.value}"
        lang_name = ru_translations.get(lang_key, lang.value.upper())
        supported_languages[lang.value] = lang_name
        
    return templates.TemplateResponse(
        "landing.html", 
        {
            "request": request, 
            "is_authenticated": is_authenticated,
            "dashboard_widgets": plugins_data.get("dashboard_widgets", []),
            "supported_languages": supported_languages,
            "active_language": active_language
        }
    )


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(
    request: Request,
    flow_id: Optional[str] = Query(None, description="ID flow для специфичной политики"),
    lang: Optional[str] = Query(None, description="Язык (ru/en)"),
):
    """Страница политики конфиденциальности"""
    
    # Определяем язык из параметра или из контекста
    if lang:
        if lang not in ["ru", "en"]:
            lang = "ru"
    else:
        # Берем из контекста если есть
        lang = getattr(request.state, 'language', 'ru')
    
    # Обновляем язык в контексте для работы t()
    context = get_context()
    if context:
        context.language = Language.RU if lang == "ru" else Language.EN
    
    # Также устанавливаем в request.state
    request.state.language = lang
    
    company_name = settings.legal.company_name_ru if lang == "ru" else settings.legal.company_name_en
    legal_form = settings.legal.legal_form_ru if lang == "ru" else settings.legal.legal_form_en
    legal_address = settings.legal.legal_address_ru if lang == "ru" else settings.legal.legal_address_en
    
    flow_info = None
    if flow_id:
        agents_container = get_frontend_container().get_agents_container()
        flow_repo = agents_container.flow_repository
        flow_config = await flow_repo.get(flow_id)
        if flow_config:
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


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(
    request: Request,
    flow_id: Optional[str] = Query(None, description="ID flow для специфичного соглашения"),
    lang: Optional[str] = Query(None, description="Язык (ru/en)"),
):
    """Страница пользовательского соглашения"""
    
    # Определяем язык из параметра или из контекста
    if lang:
        if lang not in ["ru", "en"]:
            lang = "ru"
    else:
        lang = getattr(request.state, 'language', 'ru')
    
    # Обновляем язык в контексте для работы t()
    context = get_context()
    if context:
        context.language = Language.RU if lang == "ru" else Language.EN
    
    request.state.language = lang
    
    company_name = settings.legal.company_name_ru if lang == "ru" else settings.legal.company_name_en
    legal_form = settings.legal.legal_form_ru if lang == "ru" else settings.legal.legal_form_en
    legal_address = settings.legal.legal_address_ru if lang == "ru" else settings.legal.legal_address_en
    
    flow_info = None
    if flow_id:
        agents_container = get_frontend_container().get_agents_container()
        flow_repo = agents_container.flow_repository
        flow_config = await flow_repo.get(flow_id)
        if flow_config:
            flow_info = {
                "name": flow_config.name,
                "description": flow_config.description
            }
    
    return templates.TemplateResponse(
        "terms.html",
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
            "phone": settings.legal.phone or "",
            "site_url": f"https://{settings.server.domain}",
            "domain": settings.server.domain,
            "current_date": datetime.now().strftime("%d.%m.%Y" if lang == "ru" else "%B %d, %Y"),
            "flow_info": flow_info
        }
    )

