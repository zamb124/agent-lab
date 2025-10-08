"""
Роутер для страницы чатов
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime

from app.frontend.core.template_loader import get_templates
from app.frontend.core.utils import render_with_dashboard
from app.core.flow_factory import FlowFactory

router = APIRouter(prefix="/frontend/chats", tags=["chats"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def chats_page(request: Request):
    """Главная страница чатов"""
    return await render_with_dashboard(
        request=request,
        content_template="chats.html",
        context={"request": request},
        content_url="/frontend/chats/",
    )


@router.get("/list", response_class=HTMLResponse)
async def get_chats_list(
    request: Request,
    platform: Optional[str] = Query(None),
    flow_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Получает список чатов (сессий) с фильтрацией"""
    
    flow_factory = FlowFactory()
    sessions = await flow_factory.get_flow_sessions(
        platform=platform,
        flow_id=flow_id,
        status=status,
        limit=limit,
        offset=offset
    )
    
    return templates.TemplateResponse(
        "chats_list.html",
        {
            "request": request,
            "sessions": sessions.sessions,
            "total": sessions.total,
            "limit": limit,
            "offset": offset,
            "filters": sessions.filters
        }
    )

