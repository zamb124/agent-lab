"""
Роутер модуля Chat - страницы и виджеты чата
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(prefix="/frontend/chat", tags=["chat-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def chat_page(request: Request):
    """Главная страница чата"""
    return templates.TemplateResponse("chat.html", {"request": request})


@router.get("/widget", response_class=HTMLResponse)
async def chat_widget(request: Request, agent_id: str = None, session_id: str = None):
    """Виджет чата для встраивания"""
    return templates.TemplateResponse(
        "chat_widget.html",
        {"request": request, "agent_id": agent_id, "session_id": session_id},
    )

