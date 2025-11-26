"""
Router для управления переменными компании.
"""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from apps.agents.dependencies import get_variables_service
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.utils import render_with_dashboard

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/frontend/variables", tags=["variables-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def variables_page(request: Request):
    """Главная страница управления переменными"""
    return await render_with_dashboard(
        request=request,
        content_template="variables.html",
        context={"request": request},
        content_url="/frontend/variables/list",
    )


@router.get("/list", response_class=HTMLResponse)
async def variables_list(request: Request):
    """Список переменных (HTMX endpoint)"""
    variables_service = get_variables_service()
    
    # Получаем все переменные компании
    all_vars = await variables_service.list_vars()
    
    return templates.TemplateResponse(
        "variables_list.html",
        {
            "request": request,
            "variables": all_vars
        }
    )

