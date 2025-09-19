"""
Роутер для главной страницы (лендинг)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Настройка шаблонов - включаем все необходимые директории
templates_dir = Path(__file__).parent.parent.parent / "templates"
main_templates_dir = Path(__file__).parent.parent / "templates"
chat_templates_dir = Path(__file__).parent.parent.parent / "chat" / "templates"
templates = Jinja2Templates(directory=[str(main_templates_dir), str(templates_dir), str(chat_templates_dir)])

router = APIRouter(tags=["main-pages"])


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Главная страница - лендинг Agents Lab"""
    return templates.TemplateResponse("landing.html", {"request": request})
