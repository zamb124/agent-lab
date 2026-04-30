"""
CRM Service - FastAPI приложение для управления CRM.

Порт: 8003
БД: crm_db (service) + shared_db
"""

from core.logging import get_logger
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.crm.api.router import router as api_router
from apps.crm.config import CRMSettings
from apps.crm.container import get_crm_container
from core.app import create_service_app
from core.config import get_settings
from core.context import clear_context, get_context, set_context
from core.models.context_models import Context
from core.models.identity_models import Company, User

logger = get_logger(__name__)
async def on_startup(app: FastAPI, container, settings):
    """Кастомная логика при старте"""
    from core.integrations.models import IntegrationCredential
    from core.integrations.oauth_service import set_oauth_credential_saved_hook

    set_context(Context(
        user=User(user_id="system", name="System"),
        active_company=Company(company_id="system", name="System"),
        channel="lifespan",
    ))
    try:
        await container.company_init_service.initialize_company("system")
        logger.info("Системные типы entities инициализированы для компании 'system'")
    finally:
        clear_context()

    async def _on_oauth_credential_saved(credential: IntegrationCredential) -> None:
        prev = get_context()
        set_context(
            Context(
                user=User(user_id=credential.user_id, name="OAuth"),
                active_company=Company(
                    company_id=credential.company_id,
                    name="OAuth",
                ),
                channel="integration_oauth",
            )
        )
        try:
            await container.integration_registry.dispatch_credential_saved(credential)
        finally:
            if prev is not None:
                set_context(prev)
            else:
                clear_context()

    set_oauth_credential_saved_hook(_on_oauth_credential_saved)

def create_app() -> FastAPI:
    """Создает FastAPI приложение"""
    return create_service_app(
        service_name="crm",
        settings_class=CRMSettings,
        get_container=get_crm_container,
        routers=[api_router],
        on_startup=on_startup,
        services_spa_index=Path(__file__).parent / "ui" / "index.html",
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

vendor_3d_force_graph_path = Path(__file__).parent.parent.parent / "node_modules" / "3d-force-graph" / "dist"
if vendor_3d_force_graph_path.exists():
    app.mount(
        "/crm/ui/vendor/3d-force-graph",
        StaticFiles(directory=vendor_3d_force_graph_path),
        name="crm_ui_vendor_3d_force_graph",
    )
    logger.info(f"3d-force-graph vendor смонтирован: {vendor_3d_force_graph_path}")

vendor_three_path = Path(__file__).parent.parent.parent / "node_modules" / "three" / "build"
if vendor_three_path.exists():
    app.mount(
        "/crm/ui/vendor/three",
        StaticFiles(directory=vendor_three_path),
        name="crm_ui_vendor_three",
    )
    logger.info(f"three vendor смонтирован: {vendor_three_path}")

@app.get("/crm")
@app.get("/crm/")
@app.get("/crm/{path:path}")
async def serve_crm_ui(path: str = ""):
    """Отдает главную страницу CRM UI для всех /crm/* путей (SPA fallback)"""
    if (
        path.startswith("api/")
        or path.startswith("ui/static/")
        or path.startswith("ui/vendor/")
    ):
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
