"""
Роутер модуля Bots - управление ботами
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates
from app.frontend.core.utils import render_with_dashboard
from app.db.repositories import Storage, FlowRepository
from app.models import FlowConfig
from app.core.container import get_container

router = APIRouter(prefix="/frontend/bots", tags=["bots-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def bots_page(request: Request):
    """Главная страница управления ботами"""
    return await render_with_dashboard(
        request=request,
        content_template="bots.html",
        context={"request": request},
        content_url="/frontend/bots/",
    )


@router.get("/list", response_class=HTMLResponse)
async def bots_list(request: Request):
    """Список ботов в виде карточек"""
    flow_repo = FlowRepository()
    
    flows = await flow_repo.list_all(limit=1000)
    bots = []
    
    for flow_config in flows:
        bot_info = {
            "flow_id": flow_config.flow_id,
            "name": flow_config.name,
            "description": flow_config.description if flow_config.description else '<span data-i18n="bots.no_description">Описание отсутствует</span>',
            "platforms": list(flow_config.platforms.keys()),
            "entry_point": flow_config.entry_point_agent,
        }
        bots.append(bot_info)
    
    return templates.TemplateResponse(
        "bots_list.html",
        {"request": request, "bots": bots}
    )


@router.get("/{bot_id}/details", response_class=HTMLResponse)
async def bot_details(request: Request, bot_id: str):
    """Детальная информация о боте (для раскрытой карточки)"""
    
    if bot_id == 'new':
        bot_info = {
            "flow_id": "new",
            "name": "",
            "description": "",
            "platforms": {},
            "entry_point": "",
            "timeout": None,
            "max_retries": 3,
            "prompt": "",
            "flow_variables": {},
            "local_variables": {},
            "llm_config": None,
            "rag_config": {
                "enabled": True,
                "namespace_scope": "flow",
                "search_scopes": ["flow", "company"],
                "auto_index_messages": False
            },
            "enable_reasoning": False,
            "is_new": True,
        }
        return templates.TemplateResponse(
            "bot_details.html",
            {"request": request, "bot": bot_info}
        )

    storage = get_container().storage
    flow_config = await storage.get_flow_config(bot_id)
    
    if not flow_config:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Бот не найден"}
        )
    
    agent_prompt = ""
    agent_local_variables = {}
    agent_llm_config = None
    if flow_config.entry_point_agent:
        agent_config = await storage.get_agent_config(flow_config.entry_point_agent)
        if agent_config:
            if agent_config.prompt:
                agent_prompt = agent_config.prompt
            if hasattr(agent_config, 'local_variables'):
                agent_local_variables = agent_config.local_variables or {}
            if hasattr(agent_config, 'llm_config') and agent_config.llm_config:
                agent_llm_config = agent_config.llm_config
    
    bot_info = {
        "flow_id": flow_config.flow_id,
        "name": flow_config.name,
        "description": flow_config.description or "Описание отсутствует",
        "platforms": flow_config.platforms,
        "entry_point": flow_config.entry_point_agent,
        "timeout": flow_config.timeout,
        "max_retries": flow_config.max_retries,
        "prompt": agent_prompt,
        "flow_variables": getattr(flow_config, 'variables', {}) or {},
        "local_variables": agent_local_variables,
        "llm_config": agent_llm_config,
        "rag_config": getattr(flow_config, 'rag_config', None),
        "enable_reasoning": getattr(flow_config, 'enable_reasoning', False),
        "is_new": False,
    }
    
    return templates.TemplateResponse(
        "bot_details.html",
        {"request": request, "bot": bot_info}
    )


@router.get("/platform-fields/{platform}", response_class=HTMLResponse)
async def get_platform_fields(request: Request, platform: str):
    """Получить HTML для полей конкретной платформы"""
    
    # Проверяем поддерживаемые платформы
    supported_platforms = ["whatsapp", "telegram", "amocrm", "web", "api"]
    
    if platform not in supported_platforms:
        return HTMLResponse(content="<p>Неподдерживаемая платформа</p>", status_code=404)
    
    # Для whatsapp возвращаем специальный шаблон
    if platform == "whatsapp":
        return templates.TemplateResponse(
            "platform_fields_whatsapp.html",
            {"request": request}
        )
    
    # Для остальных платформ возвращаем пустой ответ (стандартные поля уже есть)
    return HTMLResponse(content="", status_code=200)
