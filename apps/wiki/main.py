"""
Wiki Service — база знаний платформы.

Порт: 8023
БД: platform_wiki (service) + shared_db
"""

import importlib
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from apps.wiki.api import get_api_router
from apps.wiki.config import WikiSettings
from apps.wiki.container import WikiContainer, get_wiki_container
from apps.wiki.dependencies import ContainerDep
from core.app import create_service_app
from core.config import get_settings
from core.logging import get_logger

# side-effect: регистрация типов событий wiki в каталоге платформы
_ = importlib.import_module("apps.wiki.events")

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container: WikiContainer, settings: WikiSettings) -> None:
    _ = app, container, settings
    logger.info("Wiki Service: запущен")


app = create_service_app(
    service_name="wiki",
    settings_class=WikiSettings,
    get_container=get_wiki_container,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[
        get_api_router(),
    ],
    on_startup=on_startup,
    title="Wiki Service",
    description="База знаний платформы: дерево страниц внутри пространства",
    api_version="v1",
    include_crud_routers=False,
)

core_frontend_path = Path(__file__).parent.parent.parent / "core" / "frontend" / "static"
if core_frontend_path.exists():
    app.mount("/static/core", StaticFiles(directory=core_frontend_path), name="core_frontend")
    logger.info(f"Core frontend библиотека смонтирована: {core_frontend_path}")

wiki_ui_path = Path(__file__).parent / "ui"
if wiki_ui_path.exists():
    app.mount(
        "/wiki/ui/static",
        StaticFiles(directory=wiki_ui_path, html=True),
        name="wiki_ui",
    )
    logger.info(f"Wiki UI смонтирован: {wiki_ui_path}")


@app.get("/wiki")
@app.get("/wiki/")
@app.get("/wiki/{path:path}")
async def serve_wiki_ui(container: ContainerDep, path: str = "") -> FileResponse:
    """Отдаёт SPA Wiki для не-API маршрутов."""
    _ = container
    if path.startswith(("api/", "ui/static/", "ws", "assets/")):
        raise HTTPException(status_code=404, detail="Not found")
    ui_file = Path(__file__).parent / "ui" / "index.html"
    if not ui_file.exists():
        raise HTTPException(status_code=404, detail="Wiki UI not found")
    return FileResponse(ui_file)


if __name__ == "__main__":
    from core.app.server import serve

    serve("wiki", "apps.wiki.main:app", get_settings())
