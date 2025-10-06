"""
Роутер для страницы истории выполнения flow
"""

from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from typing import Optional
from datetime import datetime

from app.frontend.core.template_loader import get_templates
from app.frontend.core.utils import render_with_dashboard
from app.core.flow_factory import FlowFactory

router = APIRouter(prefix="/frontend/history", tags=["history"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def history_page(request: Request):
    """Главная страница истории"""
    return await render_with_dashboard(
        request=request,
        content_template="history.html",
        context={"request": request},
        content_url="/frontend/history/",
    )


@router.get("/sessions", response_class=HTMLResponse)
async def get_sessions_table(
    request: Request,
    platform: Optional[str] = Query(None),
    flow_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Получает таблицу сессий с фильтрацией (HTMX endpoint)"""
    
    date_from_dt = None
    date_to_dt = None
    
    if date_from:
        date_from_dt = datetime.fromisoformat(date_from)
    if date_to:
        date_to_dt = datetime.fromisoformat(date_to)
    
    flow_factory = FlowFactory()
    sessions = await flow_factory.get_flow_sessions(
        platform=platform,
        flow_id=flow_id,
        user_id=user_id,
        status=status,
        date_from=date_from_dt,
        date_to=date_to_dt,
        limit=limit,
        offset=offset
    )
    
    return templates.TemplateResponse(
        "history_sessions_table.html",
        {
            "request": request,
            "sessions": sessions.sessions,
            "total": sessions.total,
            "limit": limit,
            "offset": offset,
            "filters": sessions.filters
        }
    )


@router.get("/sessions/{session_id}/messages", response_class=HTMLResponse)
async def get_session_messages_modal(
    request: Request,
    session_id: str,
    limit: int = Query(100, ge=1, le=1000)
):
    """Получает модальное окно с историей сообщений сессии (HTMX endpoint)"""
    
    flow_factory = FlowFactory()
    history = await flow_factory.get_flow_history(
        session_id=session_id,
        limit=limit,
        include_checkpoints=False
    )
    
    return templates.TemplateResponse(
        "history_messages_modal.html",
        {
            "request": request,
            "history": history
        }
    )
