"""
Страницы авторизации и управления компаниями
"""

import json
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from apps.frontend.core.template_loader import get_templates
from core.models import AuthProvider

from core.config import settings
from core.context import get_context
from core.db.storage import Storage
from apps.frontend.container import get_frontend_container

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

    storage = get_frontend_container().storage
    user_companies = []

    for company_id, roles in user.companies.items():
        if settings.server.env == "local":
            company_url = f"http://{company_id}.localhost:{settings.server.port}/frontend/dashboard"
        else:
            company_url = f"https://{company_id}.{settings.server.domain}/frontend/dashboard"

        company_data = await storage.get(f"company:{company_id}", force_global=True)
        company_name = company_id

        if company_data:
            company_dict = json.loads(company_data) if isinstance(company_data, str) else company_data
            company_name = company_dict.get("name", company_id)

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
    return templates.TemplateResponse("create_company.html", {
        "request": request,
        "domain": settings.server.domain
    })

