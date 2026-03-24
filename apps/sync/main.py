"""
Sync Service - FastAPI приложение для инженерного чата с Git-интеграцией.

Порт: 8005
БД: sync_db (service) + shared_db
"""

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.types import Scope, Receive, Send

from core.app import create_service_app
from core.config import get_settings
from apps.sync.config import SyncSettings
from apps.sync.container import get_sync_container
from apps.sync.ws import fanout, websocket_endpoint
from apps.sync.api import get_api_router

logger = logging.getLogger(__name__)


class NoCacheStaticFiles(StaticFiles):
    """StaticFiles с Cache-Control: no-cache для браузерного сброса модулей при разработке."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response

async def on_startup(app: FastAPI, container, settings):
    """Инициализация PubSubFanout. Схема БД только через Alembic (make migrate)."""
    await fanout.start()
    logger.info("Sync Service: PubSubFanout запущен")


async def on_shutdown(app: FastAPI, container):
    """Остановка PubSubFanout."""
    await fanout.stop()
    logger.info("Sync Service: PubSubFanout остановлен")


app = create_service_app(
    service_name="sync",
    settings_class=SyncSettings,
    get_container=get_sync_container,
    routers=[
        get_api_router(),
    ],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    title="Sync Service",
    description="Инженерный чат с Git-интеграцией",
    api_version="v1",
    include_crud_routers=False,
)

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", NoCacheStaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

sync_ui_path = Path(__file__).parent / "ui"
if sync_ui_path.exists():
    app.mount("/sync/ui/static", NoCacheStaticFiles(directory=sync_ui_path, html=True), name="sync_ui")
    logger.info(f"Sync UI смонтирован: {sync_ui_path}")


@app.get("/sync/join/{token}")
async def serve_call_join(token: str):
    """Публичная страница входа в звонок по ссылке (без auth)."""
    join_file = Path(__file__).parent / "ui" / "call-join.html"
    if not join_file.exists():
        raise HTTPException(status_code=404, detail="Call join page not found")
    return FileResponse(join_file)


@app.get("/sync")
@app.get("/sync/")
@app.get("/sync/{path:path}")
async def serve_sync_ui(path: str = ""):
    """SPA fallback для Sync UI."""
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


@app.websocket("/sync/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint для realtime."""
    await websocket_endpoint(websocket)


if __name__ == "__main__":
    import uvicorn

    settings = get_settings()

    uvicorn.run(
        "apps.sync.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
