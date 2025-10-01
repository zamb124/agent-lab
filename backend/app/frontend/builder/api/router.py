"""
Главный роутер для Builder API.
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from .flows import router as flows_router
from .agents import router as agents_router
from .tools import router as tools_router

# Настройка шаблонов - включаем все необходимые директории
templates_dir = Path(__file__).parent.parent.parent / "templates"
chat_templates_dir = Path(__file__).parent.parent.parent / "chat" / "templates"
templates = Jinja2Templates(directory=[str(templates_dir), str(chat_templates_dir)])

# Главный роутер для Builder
router = APIRouter(prefix="/builder", tags=["builder"])

# Подключаем API роутеры
router.include_router(flows_router)
router.include_router(agents_router)
router.include_router(tools_router)


@router.get("/", response_class=HTMLResponse)
async def builder_index(request: Request):
    """Главная страница Builder"""
    return templates.TemplateResponse("builder/index.html", {"request": request})


@router.get("/flow/{flow_id}", response_class=HTMLResponse)
async def builder_flow(request: Request, flow_id: str):
    """Страница редактирования конкретного флоу"""
    return templates.TemplateResponse(
        "builder/index.html", 
        {"request": request, "flow_id": flow_id}
    )
