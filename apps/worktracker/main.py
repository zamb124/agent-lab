"""
Worktracker Service — платформенное ядро задач WorkItem.

Порт: 8021
БД: platform_worktracker (service) + shared_db
"""

import importlib
from pathlib import Path

from apps.worktracker.api import get_api_router
from apps.worktracker.config import WorktrackerSettings
from apps.worktracker.di import WorktrackerDi
from apps.worktracker.realtime.command_router import WORKTRACKER_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings

# side-effect: register platform event catalog types
_ = importlib.import_module("core.worktracker.events")

app = create_service_app(
    "worktracker",
    WorktrackerSettings,
    WorktrackerDi,
    database="worktracker_url",
    operations=WORKTRACKER_OPERATIONS,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    title="Worktracker Service",
    description="Платформенное ядро задач WorkItem (канбан, очереди, HITL, агентские задачи)",
    api_version="v1",
)

mount_service_spa(app, public_segment="worktracker", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("worktracker", "apps.worktracker.main:app", get_settings())
