"""Demo-сид витрин shop: спеки и реестр эталонных магазинов.

``DEMO_TEMPLATES`` — неизменяемый набор шаблонов, разворачиваемых
``ShopSeedService`` при инициализации компании и командой досева.
"""

from apps.shop.seed.spec import DemoShopSpec
from apps.shop.seed.templates.bakery import BAKERY
from apps.shop.seed.templates.cafe import CAFE
from apps.shop.seed.templates.market import MARKET
from apps.shop.seed.templates.pizza import PIZZA

DEMO_TEMPLATES: tuple[DemoShopSpec, ...] = (CAFE, BAKERY, PIZZA, MARKET)

__all__ = ["DEMO_TEMPLATES", "DemoShopSpec"]
