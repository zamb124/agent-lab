"""DI процесса shop: витрины, каталог, заказы, агрегатор."""

from typing import Annotated

from apps.shop.config import ShopSettings
from apps.shop.services.aggregate_service import AggregateService
from apps.shop.services.ai_service import ShopAiService
from apps.shop.services.domain_service import DomainService
from apps.shop.services.feed_service import FeedService
from apps.shop.services.loyalty_service import LoyaltyService
from apps.shop.services.notification_service import NotificationService
from apps.shop.services.order_events_service import OrderEventsService
from apps.shop.services.order_service import ShopOrderService
from apps.shop.services.seed_service import ShopSeedService
from apps.shop.services.shop_service import ShopService
from apps.shop.services.storefront_service import StorefrontService
from core.di import http_di, task_di
from core.di.platform import PlatformDi


class ShopDi(PlatformDi):
    settings: ShopSettings
    shop_service: ShopService
    storefront_service: StorefrontService
    order_service: ShopOrderService
    order_events_service: OrderEventsService
    notification_service: NotificationService
    domain_service: DomainService
    aggregate_service: AggregateService
    ai_service: ShopAiService
    seed_service: ShopSeedService
    feed_service: FeedService
    loyalty_service: LoyaltyService


Di = Annotated[ShopDi, http_di(ShopDi), task_di(ShopDi)]
