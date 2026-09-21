"""
Worktracker Service — платформенное ядро задач WorkItem.

Порт: 8021
БД: platform_worktracker (service) + shared_db
"""

import importlib
from pathlib import Path

from fastapi import FastAPI

from apps.worktracker.api import get_api_router
from apps.worktracker.config import WorktrackerSettings
from apps.worktracker.container import WorktrackerContainer, get_worktracker_container
from apps.worktracker.realtime.command_router import register_worktracker_ws_commands
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings
from core.logging import get_logger

# side-effect: register platform event catalog types
_ = importlib.import_module("core.worktracker.events")

logger = get_logger(__name__)


async def on_startup(
    app: FastAPI, container: WorktrackerContainer, settings: WorktrackerSettings
) -> None:
    _ = app, container, settings
    register_worktracker_ws_commands()
    logger.info("worktracker.service.command.router.op_")


app = create_service_app(
    service_name="worktracker",
    settings_class=WorktrackerSettings,
    get_container=get_worktracker_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        get_api_router(),
    ],
    on_startup=on_startup,
    title="Worktracker Service",
    description="Платформенное ядро задач WorkItem (канбан, очереди, HITL, агентские задачи)",
    api_version="v1",
    include_crud_routers=False,
)

mount_service_spa(app, public_segment="worktracker", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("worktracker", "apps.worktracker.main:app", get_settings())
