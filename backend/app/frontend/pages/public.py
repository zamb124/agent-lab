"""
Публичные страницы (landing page и т.д.)
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(tags=["public-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def landing_page(request: Request):
    """Главная страница - лендинг Agents Lab"""
    return templates.TemplateResponse("landing.html", {"request": request})

