"""
Роутер модуля Bots - управление ботами
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates
from app.core.storage import Storage
from app.models import FlowConfig

router = APIRouter(prefix="/frontend/bots", tags=["bots-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def bots_page(request: Request):
    """Главная страница управления ботами"""
    return templates.TemplateResponse("bots.html", {"request": request})


@router.get("/list", response_class=HTMLResponse)
async def bots_list(request: Request):
    """Список ботов в виде карточек"""
    storage = Storage()
    
    all_keys = await storage.list_by_prefix("flow:", limit=1000)
    bots = []
    
    for key in all_keys:
        try:
            flow_data = await storage.get(key)
            if flow_data:
                flow_config = FlowConfig.model_validate_json(flow_data)
                
                bot_info = {
                    "flow_id": flow_config.flow_id,
                    "name": flow_config.name,
                    "description": flow_config.description or "Описание отсутствует",
                    "platforms": list(flow_config.platforms.keys()),
                    "entry_point": flow_config.entry_point_agent,
                }
                bots.append(bot_info)
        except Exception as e:
            continue
    
    return templates.TemplateResponse(
        "bots_list.html",
        {"request": request, "bots": bots}
    )


@router.get("/{bot_id}/details", response_class=HTMLResponse)
async def bot_details(request: Request, bot_id: str):
    """Детальная информация о боте (для раскрытой карточки)"""
    storage = Storage()
    
    flow_config = await storage.get_flow_config(bot_id)
    
    if not flow_config:
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "error": "Бот не найден"}
        )
    
    agent_prompt = ""
    if flow_config.entry_point_agent:
        agent_config = await storage.get_agent_config(flow_config.entry_point_agent)
        if agent_config and agent_config.prompt:
            agent_prompt = agent_config.prompt
    
    bot_info = {
        "flow_id": flow_config.flow_id,
        "name": flow_config.name,
        "description": flow_config.description or "Описание отсутствует",
        "platforms": flow_config.platforms,
        "entry_point": flow_config.entry_point_agent,
        "timeout": flow_config.timeout,
        "max_retries": flow_config.max_retries,
        "prompt": agent_prompt,
    }
    
    return templates.TemplateResponse(
        "bot_details.html",
        {"request": request, "bot": bot_info}
    )
