"""
Главная страница dashboard
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates
from app.frontend.core.plugin_loader import get_plugins_for_template

router = APIRouter(prefix="/frontend", tags=["dashboard-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Панель управления с динамической загрузкой плагинов"""
    plugin_data = get_plugins_for_template(request)
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "preload_url": "/frontend/dashboard/welcome",
        **plugin_data
    })


@router.get("/dashboard/welcome", response_class=HTMLResponse)
async def dashboard_welcome(request: Request):
    """Приветственное сообщение на главной странице"""
    return templates.TemplateResponse("welcome.html", {"request": request})


@router.get("/fashn", response_class=HTMLResponse)
async def fashn_page(request: Request):
    """Страница FASHN виртуальной примерки"""
    return templates.TemplateResponse("fashn.html", {"request": request})

