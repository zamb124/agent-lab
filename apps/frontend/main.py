"""
Frontend Service - FastAPI приложение для управления платформой
"""
import logging
import json
import os
import re
from pathlib import Path
from typing import Optional, Dict, Any
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

logger = logging.getLogger(__name__)

SYSTEM_COMPANY_ID = "system"
SYSTEM_ADMIN_EMAIL = "zambas124@yandex.ru"
ADMIN_ROLE = "admin"


async def _ensure_system_admin_membership(container: object) -> None:
    system_company = await container.company_repository.get(SYSTEM_COMPANY_ID)
    if system_company is None:
        raise ValueError("System company not found")

    users = await container.user_repository.list_all(limit=10000)
    matched_users = [user for user in users if SYSTEM_ADMIN_EMAIL in user.emails]
    if not matched_users:
        raise ValueError(f"User with email {SYSTEM_ADMIN_EMAIL} not found")
    if len(matched_users) > 1:
        matched_user_ids = ", ".join(user.user_id for user in matched_users)
        raise ValueError(f"Multiple users found for {SYSTEM_ADMIN_EMAIL}: {matched_user_ids}")

    target_user = matched_users[0]
    company_roles = system_company.members.get(target_user.user_id, [])
    user_roles = target_user.companies.get(system_company.company_id, [])
    company_needs_update = ADMIN_ROLE not in company_roles
    user_needs_update = ADMIN_ROLE not in user_roles

    if not company_needs_update and not user_needs_update:
        logger.info(
            "Bootstrap check passed: %s already has admin rights in %s",
            SYSTEM_ADMIN_EMAIL,
            system_company.company_id,
        )
        return

    if company_needs_update:
        system_company.members[target_user.user_id] = [*company_roles, ADMIN_ROLE]
    if user_needs_update:
        target_user.companies[system_company.company_id] = [*user_roles, ADMIN_ROLE]

    await container.company_repository.set(system_company)
    await container.user_repository.set(target_user)
    logger.info(
        "Bootstrap updated: granted admin role for %s in company %s",
        SYSTEM_ADMIN_EMAIL,
        system_company.company_id,
    )


async def on_startup(app: FastAPI, container, settings: FrontendSettings) -> None:
    if os.getenv("TESTING") == "true":
        return
    await _ensure_system_admin_membership(container)


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


@app.get("/api/i18n/{locale}")
async def get_translations(locale: str) -> JSONResponse:
    """
    Получение переводов для указанной локали
    
    Args:
        locale: Код языка (ru, en)
    
    Returns:
        JSON с переводами для всех namespace
    """
    if locale not in ["ru", "en"]:
        raise HTTPException(status_code=400, detail="Unsupported locale")
    
    translations_path = Path(__file__).parent.parent.parent / "core" / "i18n" / "translations" / locale
    
    if not translations_path.exists():
        raise HTTPException(status_code=404, detail=f"Translations not found for locale: {locale}")
    
    translations: Dict[str, Any] = {}
    
    for file_path in translations_path.glob("*.json"):
        namespace = file_path.stem
        
        if namespace.startswith("_"):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                translations[namespace] = json.load(f)
        except Exception as e:
            logger.error(f"Error loading translation file {file_path}: {e}")
            continue
    
    return JSONResponse(content=translations)


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

