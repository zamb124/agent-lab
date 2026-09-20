"""
Wiki Service — база знаний платформы.

Порт: 8023
БД: platform_wiki (service) + shared_db
"""

import importlib
from pathlib import Path

from fastapi import FastAPI

from apps.wiki.api import get_api_router
from apps.wiki.config import WikiSettings
from apps.wiki.container import WikiContainer, get_wiki_container
from apps.wiki.realtime.command_router import register_wiki_ws_commands
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings
from core.logging import get_logger

# side-effect: регистрация типов событий wiki в каталоге платформы
_ = importlib.import_module("apps.wiki.events")

logger = get_logger(__name__)


async def on_startup(app: FastAPI, container: WikiContainer, settings: WikiSettings) -> None:
    _ = app, container, settings
    register_wiki_ws_commands()
    logger.info("Wiki Service: command-router op_* зарегистрирован")


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

mount_service_spa(app, public_segment="wiki", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("wiki", "apps.wiki.main:app", get_settings())
