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
    plugin_data = get_plugins_for_template()
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        **plugin_data
    })


@router.get("/fashn", response_class=HTMLResponse)
async def fashn_page(request: Request):
    """Страница FASHN виртуальной примерки"""
    return templates.TemplateResponse("fashn.html", {"request": request})

