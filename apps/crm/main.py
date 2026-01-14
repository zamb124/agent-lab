"""
CRM Service - FastAPI приложение для управления CRM.

Порт: 8003
БД: crm_db (service) + shared_db
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from core.app import create_service_app
from core.config import get_settings
from apps.crm.config import CRMSettings
from apps.crm.container import get_crm_container

logger = logging.getLogger(__name__)


async def on_startup(app: FastAPI, container, settings):
    """Кастомная логика при старте"""
    await container.company_init_service.initialize_company("system")
    logger.info("Системные типы entities инициализированы для компании 'system'")


# Импорт роутера
from apps.crm.api.router import router as api_router


def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    return create_service_app(
        service_name="crm",
        settings_class=CRMSettings,
        get_container=get_crm_container,
        routers=[api_router],
        on_startup=on_startup,
        title="CRM Service",
        description="API для управления CRM: сущности, заметки, задачи, связи",
        include_crud_routers=False,
    )


app = create_app()

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

crm_ui_path = Path(__file__).parent / "ui"
if crm_ui_path.exists():
    app.mount("/crm/ui/static", StaticFiles(directory=crm_ui_path, html=True), name="crm_ui")
    logger.info(f"CRM UI смонтирован: {crm_ui_path}")

@app.get("/crm")
@app.get("/crm/")
@app.get("/crm/{path:path}")
async def serve_crm_ui(path: str = ""):
    """Отдает главную страницу CRM UI для всех /crm/* путей (SPA fallback)"""
    if path.startswith("api/") or path.startswith("ui/static/"):
        raise HTTPException(status_code=404, detail="Not found")
    
    ui_file = Path(__file__).parent / "ui" / "index.html"
    if not ui_file.exists():
        raise HTTPException(status_code=404, detail="CRM UI not found")
    return FileResponse(ui_file)


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "apps.crm.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
