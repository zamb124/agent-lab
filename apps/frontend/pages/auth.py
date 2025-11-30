"""
Страницы авторизации и управления компаниями
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.frontend.core.template_loader import get_templates
from apps.frontend.container import get_frontend_container
from core.models import AuthProvider
from core.config import get_settings
from core.context import get_context

router = APIRouter(prefix="/frontend", tags=["auth-pages"])
templates = get_templates()


@router.get("/auth", response_class=HTMLResponse)
async def auth_page(request: Request):
    """Страница авторизации"""
    providers = [{"value": p.value, "name": p.value.title()} for p in AuthProvider]
    return templates.TemplateResponse(
        "auth.html", {"request": request, "providers": providers}
    )


@router.get("/select-company", response_class=HTMLResponse)
async def select_company_page(request: Request):
    """Страница выбора компании"""
    context = get_context()
    user = context.user if context else None

    if not user or not user.companies:
        return RedirectResponse(url="/frontend/create-company")

    settings = get_settings()
    company_repo = get_frontend_container().company_repository
    user_companies = []

    protocol = "http" if settings.server.env == "local" else "https"
    for company_id, roles in user.companies.items():
        company_url = f"{protocol}://{company_id}.{settings.server.domain}/frontend/dashboard"

        company = await company_repo.get(company_id)
        company_name = company.name if company else company_id

        user_companies.append({
            "name": company_name,
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
    settings = get_settings()
    return templates.TemplateResponse("create_company.html", {
        "request": request,
        "domain": settings.server.domain
    })
