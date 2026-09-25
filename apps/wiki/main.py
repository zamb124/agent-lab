"""
Wiki Service — база знаний платформы.

Порт: 8023
БД: platform_wiki (service) + shared_db
"""

import importlib
from pathlib import Path

from apps.wiki.api import get_api_router
from apps.wiki.config import WikiSettings
from apps.wiki.di import WikiDi
from apps.wiki.realtime.command_router import WIKI_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings

# side-effect: регистрация типов событий wiki в каталоге платформы
_ = importlib.import_module("apps.wiki.events")

app = create_service_app(
    "wiki",
    WikiSettings,
    WikiDi,
    database="wiki_url",
    operations=WIKI_OPERATIONS,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    title="Wiki Service",
    description="База знаний платформы: дерево страниц внутри пространства",
    api_version="v1",
)

mount_service_spa(app, public_segment="wiki", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("wiki", "apps.wiki.main:app", get_settings())
