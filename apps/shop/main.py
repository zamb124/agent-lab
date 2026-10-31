"""
Shop Service — витрины и агрегатор интернет-магазинов платформы.

Порт: 8027
БД: platform_shop (service) + shared_db
"""

import importlib

from apps.shop.api import get_api_router
from apps.shop.config import ShopSettings
from apps.shop.di import ShopDi
from apps.shop.realtime.command_router import SHOP_OPERATIONS
from core.app import create_service_app
from core.config import get_settings

# side-effect: регистрация типов событий shop в каталоге платформы
_ = importlib.import_module("apps.shop.events")

app = create_service_app(
    "shop",
    ShopSettings,
    ShopDi,
    database="shop_url",
    operations=SHOP_OPERATIONS,
    routers=[get_api_router()],
    title="Shop Service",
    description="Витрины интернет-магазинов и публичный агрегатор поиска",
    api_version="v1",
)

_settings = get_settings()
if isinstance(_settings, ShopSettings):
    from apps.shop.host_middleware import StorefrontHostMiddleware

    app.add_middleware(
        StorefrontHostMiddleware,
        domain_suffix=_settings.storefront_domain_suffix,
        reserved=_settings.reserved_slugs,
    )


if __name__ == "__main__":
    from core.app.server import serve

    serve("shop", "apps.shop.main:app", get_settings())
