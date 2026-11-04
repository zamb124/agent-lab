"""
Shop Service — витрины и агрегатор интернет-магазинов платформы.

Порт: 8027
БД: platform_shop (service) + shared_db
"""

import importlib
from pathlib import Path

from apps.shop.api import get_api_router
from apps.shop.config import ShopSettings
from apps.shop.di import ShopDi
from apps.shop.host_middleware import StorefrontHostMiddleware
from apps.shop.realtime.command_router import SHOP_OPERATIONS
from core.app import create_service_app
from core.app.spa import mount_service_spa
from core.config import get_settings

# side-effect: регистрация типов событий shop в каталоге платформы
_ = importlib.import_module("apps.shop.events")

_settings = get_settings()

app = create_service_app(
    "shop",
    ShopSettings,
    ShopDi,
    database="shop_url",
    operations=SHOP_OPERATIONS,
    services_spa_index=Path(__file__).parent / "ui" / "index.html",
    routers=[get_api_router()],
    outer_middlewares=(
        [
            (
                StorefrontHostMiddleware,
                {
                    "domain_suffix": _settings.storefront_domain_suffix,
                    "aggregator_host": _settings.aggregator_host,
                },
            )
        ]
        if isinstance(_settings, ShopSettings)
        else None
    ),
    title="Shop Service",
    description="Витрины интернет-магазинов и публичный агрегатор поиска",
    api_version="v1",
)

mount_service_spa(app, public_segment="shop", ui_dir=Path(__file__).parent / "ui")


if __name__ == "__main__":
    from core.app.server import serve

    serve("shop", "apps.shop.main:app", get_settings())
