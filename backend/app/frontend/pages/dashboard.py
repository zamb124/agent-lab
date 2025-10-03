"""
Главная страница dashboard и страницы моделей
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(prefix="/frontend", tags=["dashboard-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Панель управления"""
    return templates.TemplateResponse("dashboard.html", {"request": request})


@router.get("/models/{model_type}", response_class=HTMLResponse)
async def model_page(request: Request, model_type: str, view: str = "table"):
    """Страница модели - показывает dashboard с предзагруженным контентом"""
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "preload_url": f"/frontend/models/{model_type}?view={view}",
        },
    )


@router.get("/fashn", response_class=HTMLResponse)
async def fashn_page(request: Request):
    """Страница FASHN виртуальной примерки"""
    return templates.TemplateResponse("fashn.html", {"request": request})

