"""
Роутер модуля Abilities - страница способностей
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates
from app.frontend.core.utils import render_with_dashboard
from app.frontend.dependencies import StorageDep, AgentRepositoryDep

router = APIRouter(prefix="/frontend/abilities", tags=["abilities-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def abilities_page(request: Request):
    """Главная страница способностей"""
    return await render_with_dashboard(
        request=request,
        content_template="abilities.html",
        context={"request": request},
        content_url="/frontend/abilities/",
    )


@router.get("/list", response_class=HTMLResponse)
async def abilities_list(
    request: Request,
    storage: StorageDep,
    agent_repo: AgentRepositoryDep
):
    """Список способностей (агенты + тулы) для HTMX"""
    from app.models import ToolReference
    import json
    
    agents = []
    tools = []
    
    # Оптимизация: получаем всех агентов за 1 запрос
    all_agents_data = await storage.get_all_by_prefix("agent:", limit=1000)
    for key, agent_data_json in all_agents_data.items():
        try:
            from app.models import AgentConfig
            agent = AgentConfig.model_validate_json(agent_data_json)
            if getattr(agent, 'is_public', False):
                agents.append({
                    "id": agent.agent_id,
                    "name": agent.title or agent.name or agent.agent_id,
                    "description": agent.description or "Агент без описания",
                    "type": "agent",
                    "agent_type": agent.type.value if hasattr(agent.type, 'value') else str(agent.type),
                })
        except Exception:
            continue
    
    # Оптимизация: получаем все тулы за 1 запрос
    all_tools_data = await storage.get_all_by_prefix("tool:", limit=1000)
    for key, tool_data_json in all_tools_data.items():
        tool_prefix_index = key.find(":tool:")
        if tool_prefix_index != -1:
            tool_id = key[tool_prefix_index + 6:]
        else:
            continue
        
        if isinstance(tool_data_json, str):
            tool_data = json.loads(tool_data_json)
        else:
            tool_data = tool_data_json
        
        is_public = tool_data.get("is_public", False)
        if is_public:
            tools.append({
                "id": tool_id,
                "name": tool_data.get("title") or tool_id.split(".")[-1],
                "description": tool_data.get("description", "Инструмент без описания"),
                "type": "tool",
                "cost": tool_data.get("cost", 0.0),
            })
    
    return templates.TemplateResponse("abilities_list.html", {
        "request": request,
        "agents": agents,
        "tools": tools,
    })

