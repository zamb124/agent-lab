"""
Страницы авторизации и управления компаниями
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from apps.frontend.core.template_loader import get_templates
from apps.frontend.container import get_frontend_container
from core.models import AuthProvider
from core.context import get_context
from core.utils.domain import build_url, get_host_with_port

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

    company_repo = get_frontend_container().company_repository
    user_companies = []

    host = context.host
    for company_id, roles in user.companies.items():
        company_url = build_url(host, "/frontend/dashboard", subdomain=company_id)

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
        "domain": get_host_with_port(host),
        "user_companies": user_companies
    })


@router.get("/create-company", response_class=HTMLResponse)
async def create_company_page(request: Request):
    """Страница создания компании"""
    context = get_context()
    host = context.host if context else request.headers.get("host", "")
    
    return templates.TemplateResponse("create_company.html", {
        "request": request,
        "domain": get_host_with_port(host)
    })
