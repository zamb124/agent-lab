"""
Worktracker Service — платформенное ядро задач WorkItem.

Порт: 8021
БД: platform_worktracker (service) + shared_db
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.worktracker.api import get_api_router
from apps.worktracker.config import WorktrackerSettings
from apps.worktracker.container import WorktrackerContainer, get_worktracker_container
from apps.worktracker.dependencies import ContainerDep
from core.app import create_service_app
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)


async def on_startup(
    app: FastAPI, container: WorktrackerContainer, settings: WorktrackerSettings
) -> None:
    _ = app, container, settings
    logger.info("Worktracker Service: запущен")


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

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

worktracker_ui_path = Path(__file__).parent / "ui"
if worktracker_ui_path.exists():
    app.mount(
        "/worktracker/ui/static",
        StaticFiles(directory=worktracker_ui_path, html=True),
        name="worktracker_ui",
    )
    logger.info(f"Worktracker UI смонтирован: {worktracker_ui_path}")


@app.get("/worktracker")
@app.get("/worktracker/")
@app.get("/worktracker/{path:path}")
async def serve_worktracker_ui(container: ContainerDep, path: str = "") -> FileResponse:
    """Отдаёт SPA Worktracker UI для не-API маршрутов."""
    _ = container
    if path.startswith(("api/", "ui/static/", "ws", "assets/")):
        raise HTTPException(status_code=404, detail="Not found")
    ui_file = Path(__file__).parent / "ui" / "index.html"
    if not ui_file.exists():
        raise HTTPException(status_code=404, detail="Worktracker UI not found")
    return FileResponse(ui_file)


if __name__ == "__main__":
    from core.app.server import serve

    serve("worktracker", "apps.worktracker.main:app", get_settings())
