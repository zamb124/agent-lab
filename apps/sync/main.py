"""
Sync Service - FastAPI приложение для инженерного чата с Git-интеграцией.

Порт: 8005
БД: sync_db (service) + shared_db
"""

import importlib
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse

from apps.sync.api import get_api_router
from apps.sync.config import SyncSettings
from apps.sync.di import SyncDi
from apps.sync.realtime.command_router import SYNC_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings
from core.di import recipe
from core.logging import get_logger

# side-effect: register platform event catalog types
_ = importlib.import_module("apps.sync.events")

logger = get_logger(__name__)


async def log_sync_startup() -> None:
    logger.info("sync.service.command.router.op_")


app = create_service_app(
    "sync",
    SyncSettings,
    SyncDi,
    database="sync_url",
    operations=SYNC_OPERATIONS,
    lifecycle=(recipe(log_sync_startup),),
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    title="Sync Service",
    description="Инженерный чат с Git-интеграцией",
    api_version="v1",
)


@app.get("/sync/join/{token}")
async def serve_call_join(token: str) -> FileResponse:
    """Публичная страница входа в звонок по ссылке (без auth). SPA: sync-app, маршрут call_join."""
    _ = token
    ui_index = Path(__file__).parent / "ui" / "index.html"
    if not ui_index.exists():
        raise HTTPException(status_code=404, detail="Sync UI not found")
    return FileResponse(ui_index)


mount_service_spa(
    app,
    public_segment="sync",
    ui_dir=Path(__file__).parent / "ui",
    excluded_prefixes=("api/", "ui/static/", "ws", "assets/", "join/"),
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("sync", "apps.sync.main:app", get_settings())
