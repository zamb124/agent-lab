"""
Router для управления MCP серверами
"""

import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse


from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.utils import render_with_dashboard
from apps.frontend.container import get_frontend_container

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frontend/mcp", tags=["mcp-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def mcp_page(request: Request):
    """Главная страница управления MCP серверами"""
    return await render_with_dashboard(
        request=request,
        content_template="mcp.html",
        context={"request": request},
        content_url="/frontend/mcp/list",
    )


@router.get("/list", response_class=HTMLResponse)
async def mcp_servers_list(request: Request):
    """Список MCP серверов (HTMX endpoint)"""
    agents_container = get_frontend_container().get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    
    servers = await mcp_repo.list_all()
    
    return templates.TemplateResponse(
        "mcp_servers_list.html",
        {
            "request": request,
            "servers": servers
        }
    )


@router.get("/{server_id}/details", response_class=HTMLResponse)
async def server_details(request: Request, server_id: str):
    """Детальная информация о MCP сервере"""
    
    if server_id == 'new':
        server_info = {
            "server_id": "",
            "name": "",
            "description": "",
            "url": "",
            "transport_type": "http",
            "headers": {},
            "timeout": 30,
            "is_active": True,
            "auto_sync_tools": True,
            "cached_tools": [],
            "last_sync_at": None,
            "is_new": True,
        }
        return templates.TemplateResponse(
            "mcp_server_details.html",
            {"request": request, "server": server_info}
        )
    
    agents_container = get_frontend_container().get_agents_container()
    mcp_repo = agents_container.mcp_server_repository
    server = await mcp_repo.get(server_id)
    
    if not server:
        raise HTTPException(status_code=404, detail="MCP сервер не найден")
    
    server_info = {
        "server_id": server.server_id,
        "name": server.name,
        "description": server.description or "",
        "url": server.url,
        "transport_type": server.transport_type,
        "headers": server.headers,
        "timeout": server.timeout,
        "is_active": server.is_active,
        "auto_sync_tools": server.auto_sync_tools,
        "cached_tools": server.cached_tools,
        "last_sync_at": server.last_sync_at.isoformat() if server.last_sync_at else None,
        "is_new": False,
    }
    
    return templates.TemplateResponse(
        "mcp_server_details.html",
        {"request": request, "server": server_info}
    )


