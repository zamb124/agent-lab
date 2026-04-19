"""
Sync Service - FastAPI приложение для инженерного чата с Git-интеграцией.

Порт: 8005
БД: sync_db (service) + shared_db
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.sync.api import get_api_router
from apps.sync.config import SyncSettings
from apps.sync.container import get_sync_container
from apps.sync.dependencies import ContainerDep
from apps.sync.realtime.command_router import register_sync_ws_commands
from apps.sync.realtime.presence_hooks import register_presence_hooks
from apps.sync.realtime.read_handlers import register_sync_ws_read_handlers
from core.app import create_service_app
from core.config import get_settings

logger = logging.getLogger(__name__)


async def on_startup(app: FastAPI, container, settings):
    """Регистрация WS command-handler'ов и presence hook'ов в core.websocket.

    Сам WS-сокет /sync/api/ws/notifications поднимает `core.websocket.router`
    через `create_service_app`. Push-события идут через `platform:ui_events`
    (см. `architecture.mdc`, раздел «REST-зеркало команд»).
    """
    register_sync_ws_commands()
    register_sync_ws_read_handlers()
    register_presence_hooks()
    logger.info("Sync Service: WS command-router и presence hooks готовы")


app = create_service_app(
    service_name="sync",
    settings_class=SyncSettings,
    get_container=get_sync_container,
    routers=[
        get_api_router(),
    ],
    on_startup=on_startup,
    title="Sync Service",
    description="Инженерный чат с Git-интеграцией",
    api_version="v1",
    include_crud_routers=False,
)

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

sync_ui_path = Path(__file__).parent / "ui"
if sync_ui_path.exists():
    app.mount("/sync/ui/static", StaticFiles(directory=sync_ui_path, html=True), name="sync_ui")
    logger.info(f"Sync UI смонтирован: {sync_ui_path}")


@app.get("/sync/join/{token}")
async def serve_call_join(container: ContainerDep, token: str):
    """Публичная страница входа в звонок по ссылке (без auth)."""
    _ = container
    join_file = Path(__file__).parent / "ui" / "call-join.html"
    if not join_file.exists():
        raise HTTPException(status_code=404, detail="Call join page not found")
    return FileResponse(join_file)


@app.get("/sync")
@app.get("/sync/")
@app.get("/sync/{path:path}")
async def serve_sync_ui(container: ContainerDep, path: str = ""):
    """SPA fallback для Sync UI."""
    _ = container
    if (
        path.startswith("api/")
        or path.startswith("ui/static/")
        or path.startswith("ws")
        or path.startswith("assets/")
        or path.startswith("join/")
    ):
        raise HTTPException(status_code=404, detail="Not found")

    ui_file = Path(__file__).parent / "ui" / "index.html"
    if not ui_file.exists():
        raise HTTPException(status_code=404, detail="Sync UI not found")
    return FileResponse(ui_file)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "apps.sync.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
