"""
Stock Service — складской учёт платформы (WMS).

Порт: 8026
БД: platform_stock (service) + shared_db
"""

import importlib
from pathlib import Path

from apps.stock.api import get_api_router
from apps.stock.config import StockSettings
from apps.stock.di import StockDi
from apps.stock.realtime.command_router import STOCK_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings

# side-effect: регистрация типов событий stock в каталоге платформы
_ = importlib.import_module("apps.stock.events")

app = create_service_app(
    "stock",
    StockSettings,
    StockDi,
    database="stock_url",
    operations=STOCK_OPERATIONS,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    title="Stock Service",
    description="Складской учёт: леджер движений, остатки, оценка стоимости",
    api_version="v1",
)

mount_service_spa(
    app,
    public_segment="stock",
    ui_dir=Path(__file__).parent / "ui",
    spa_pages={"tsd": "tsd.html"},
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("stock", "apps.stock.main:app", get_settings())
