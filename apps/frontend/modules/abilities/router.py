"""
Роутер модуля Abilities - страница способностей
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.utils import render_with_dashboard
from apps.frontend.dependencies import AgentRepositoryDep, ToolRepositoryDep

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
    agent_repo: AgentRepositoryDep,
    tool_repo: ToolRepositoryDep
):
    """Список способностей (агенты + тулы) для HTMX"""
    agents = []
    tools = []
    
    all_agents = await agent_repo.list_all(limit=1000)
    for agent in all_agents:
        if getattr(agent, 'is_public', False):
            agents.append({
                "id": agent.agent_id,
                "name": agent.title or agent.name or agent.agent_id,
                "description": agent.description or "Агент без описания",
                "type": "agent",
                "agent_type": agent.type.value if hasattr(agent.type, 'value') else str(agent.type),
            })
    
    all_tools = await tool_repo.list_all(limit=1000)
    for tool in all_tools:
        is_public = getattr(tool, "is_public", False)
        if is_public:
            tools.append({
                "id": tool.tool_id,
                "name": tool.title or tool.tool_id.split(".")[-1],
                "description": tool.description or "Инструмент без описания",
                "type": "tool",
                "cost": tool.cost,
            })
    
    return templates.TemplateResponse("abilities_list.html", {
        "request": request,
        "agents": agents,
        "tools": tools,
    })

