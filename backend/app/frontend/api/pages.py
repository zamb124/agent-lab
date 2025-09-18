"""
Роутер для фронтенд страниц
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from app.identity.models import AuthProvider

# Настройка шаблонов - включаем и общие шаблоны, и шаблоны чата
templates_dir = Path(__file__).parent.parent / "templates"
chat_templates_dir = Path(__file__).parent.parent / "chat" / "templates"
templates = Jinja2Templates(directory=[str(templates_dir), str(chat_templates_dir)])

router = APIRouter(prefix="/frontend", tags=["frontend-pages"])


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница"""
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    """Страница авторизации"""
    # Получаем список провайдеров из enum
    providers = [{"value": p.value, "name": p.value.title()} for p in AuthProvider]

    return templates.TemplateResponse(
        "auth.html", {"request": request, "providers": providers}
    )


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
