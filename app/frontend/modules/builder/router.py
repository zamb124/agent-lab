"""
Роутер модуля Builder - страницы редактирования flows
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from app.frontend.core.template_loader import get_templates

router = APIRouter(prefix="/frontend/builder", tags=["builder-pages"])
templates = get_templates()


@router.get("/", response_class=HTMLResponse)
async def builder_index(request: Request):
    """Главная страница Builder"""
    return templates.TemplateResponse("builder.html", {"request": request})


@router.get("/flow/{flow_id}", response_class=HTMLResponse)
async def builder_flow(request: Request, flow_id: str):
    """Страница редактирования конкретного флоу"""
    return templates.TemplateResponse(
        "builder.html", 
        {"request": request, "flow_id": flow_id}
    )

