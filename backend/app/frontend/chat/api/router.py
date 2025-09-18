"""
Роутер для чата - изолированный API для работы с чатом
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import os

router = APIRouter()

# Шаблоны для чата - включаем и общие шаблоны, и шаблоны чата
frontend_templates = os.path.join(os.path.dirname(__file__), "../../templates")
chat_templates = os.path.join(os.path.dirname(__file__), "../templates")
templates = Jinja2Templates(directory=[frontend_templates, chat_templates])


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
