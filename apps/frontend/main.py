"""
Frontend Service - FastAPI приложение для управления платформой
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, field_validator
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from apps.frontend.api.auth import router as auth_router
from apps.frontend.api.companies import router as companies_router
from apps.frontend.api.embed_configs import router as embed_configs_router
from apps.frontend.api.invites import router as invites_router
from apps.frontend.api.team import router as team_router
from apps.frontend.api.api_keys import router as api_keys_router
from apps.frontend.api.billing import router as billing_router
from apps.frontend.api.settings import router as settings_router
from apps.frontend.api.services import router as services_router
from apps.frontend.api.scheduler import router as scheduler_router
from apps.frontend.container import get_frontend_container
from apps.frontend.config import FrontendSettings, get_frontend_settings
from core.app.factory import create_service_app
from core.identity.system_bootstrap import ensure_system_admin_membership

logger = logging.getLogger(__name__)

async def on_startup(app: FastAPI, container, settings: FrontendSettings) -> None:
    if os.getenv("TESTING") == "true":
        return
    await ensure_system_admin_membership(container)


# Создаем приложение через фабрику (автоматически подключает middleware, контейнер и т.д.)
app = create_service_app(
    service_name="frontend",
    settings_class=FrontendSettings,
    get_container=get_frontend_container,
    on_startup=on_startup,
    pages_routers=[
        auth_router,
        companies_router,
        embed_configs_router,
        invites_router,
        team_router,
        api_keys_router,
        billing_router,
        settings_router,
        services_router,
        scheduler_router,
    ],
    title="Platform Management",
    description="Управление платформой: авторизация, компании, биллинг",
    version="1.0.0",
    api_version=None,
    include_crud_routers=False,
    mkdocs_gateway_prefix="frontend",
)

# Монтирование core/frontend (общая библиотека) - СНАЧАЛА монтируем статику!
core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount(
        "/static/core",
        StaticFiles(directory=str(core_frontend_path)),
        name="core-frontend"
    )
    logger.info(f"✅ Core frontend библиотека: {core_frontend_path}")

# Монтирование apps/frontend/ui (само приложение)
ui_path = Path(__file__).parent / "ui"
if ui_path.exists():
    app.mount(
        "/static/frontend",
        StaticFiles(directory=str(ui_path)),
        name="frontend-ui"
    )
    logger.info(f"✅ Frontend UI: {ui_path}")

# Удаляем дефолтный root endpoint от фабрики - ПОСЛЕ монтирования статики
# (он возвращает {"service": "core", "version": "1.0.0", "status": "running"})
# Заменим его на SPA fallback ниже
for route in list(app.routes):
    if hasattr(route, 'path') and route.path == "/":
        app.routes.remove(route)


class LeadRequest(BaseModel):
    name: str
    email: str
    phone: Optional[str] = None
    company: Optional[str] = None
    comment: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_regex, v):
            raise ValueError('Invalid email format')
        return v


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "frontend"}


@app.post("/api/leads")
async def create_lead(lead: LeadRequest):
    """
    Обработка заявки с лендинга
    
    В production версии здесь должна быть:
    - Валидация данных
    - Сохранение в БД
    - Отправка уведомления в CRM/Email/Telegram
    """
    logger.info(f"Новая заявка: {lead.name} ({lead.email})")
    
    # TODO: Сохранение в БД
    # TODO: Отправка уведомления
    
    return {
        "success": True,
        "message": "Заявка принята. Мы свяжемся с вами в ближайшее время."
    }


@app.get("/api/public/legal")
@app.get("/frontend/api/public/legal")
async def get_public_legal() -> JSONResponse:
    """Публичные юридические реквизиты для страниц policy/terms."""
    legal = get_frontend_settings().legal.model_dump()
    return JSONResponse(content=legal)


# SPA fallback (все неизвестные пути → index.html)
@app.get("/")
@app.get("/{full_path:path}")
async def serve_spa(full_path: str = ""):
    # Исключаем API, статику, WebSocket и PWA файлы
    # full_path может начинаться с frontend/ из-за префикса сервиса
    excluded = (
        "api/", "static/", "ws/",
        "documentation/", "documentation",
        "frontend/api/", "frontend/static/", "frontend/ws/",
        "frontend/documentation/", "frontend/documentation",
        "manifest.json", "sw.js", "offline.html"
    )
    if full_path.startswith(excluded) or full_path in ("manifest.json", "sw.js", "offline.html"):
        raise HTTPException(status_code=404)
    
    index_path = ui_path / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    
    return {"message": "Frontend UI not built yet"}


if __name__ == "__main__":
    import uvicorn
    from apps.frontend.config import get_frontend_settings
    
    settings = get_frontend_settings()
    uvicorn.run(
        "apps.frontend.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )

