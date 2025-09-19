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


@router.get("/select-company", response_class=HTMLResponse)
async def select_company_page(request: Request):
    """Страница выбора компании"""
    from app.core.config import settings
    from app.core.context import get_context
    
    context = get_context()
    user = context.user if context else None
    
    if not user or not user.companies:
        # Если нет компаний - редирект на создание
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/frontend/create-company")
    
    # Формируем список компаний с URL
    from app.core.storage import Storage
    storage = Storage()
    
    user_companies = []
    for company_id, roles in user.companies.items():
        if settings.server.env == "local":
            company_url = f"http://{company_id}.localhost:8001/frontend/dashboard"
        else:
            company_url = f"http://{company_id}.{settings.server.domain}/frontend/dashboard"
        
        # Загружаем название компании из БД
        company_data = await storage.get(f"company:{company_id}", force_global=True)
        company_name = company_id  # Дефолтное название
        if company_data:
            import json
            company_dict = json.loads(company_data) if isinstance(company_data, str) else company_data
            company_name = company_dict.get("name", company_id)
        
        user_companies.append({
            "name": company_name,  # Реальное название компании
            "subdomain": company_id,
            "roles": roles,
            "url": company_url
        })
    
    return templates.TemplateResponse("select_company.html", {
        "request": request,
        "domain": settings.server.domain,
        "user_companies": user_companies
    })


@router.get("/create-company", response_class=HTMLResponse)
async def create_company_page(request: Request):
    """Страница создания компании"""
    from app.core.config import settings
    return templates.TemplateResponse("create_company.html", {
        "request": request, 
        "domain": settings.server.domain
    })


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
