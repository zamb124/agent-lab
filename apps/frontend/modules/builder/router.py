"""
Роутер модуля Builder - страницы редактирования flows
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from apps.frontend.core.template_loader import get_templates
from apps.frontend.core.plugin_loader import get_plugins_for_template

router = APIRouter(prefix="/frontend/builder", tags=["builder-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def builder_index(request: Request):
    """Главная страница Builder"""
    plugin_data = get_plugins_for_template(request)
    return templates.TemplateResponse("builder.html", {
        "request": request,
        **plugin_data
    })


@router.get("/flow/{flow_id:path}", response_class=HTMLResponse)
async def builder_flow(request: Request, flow_id: str):
    """Страница редактирования конкретного флоу"""
    plugin_data = get_plugins_for_template(request)
    return templates.TemplateResponse("builder.html", {
        "request": request,
        "flow_id": flow_id,
        **plugin_data
    })

