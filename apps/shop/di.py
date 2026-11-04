"""DI процесса shop: витрины, каталог, заказы, агрегатор, импорт меню."""

from typing import Annotated

from apps.shop.config import ShopSettings
from apps.shop.services.aggregate_service import AggregateService
from apps.shop.services.ai_service import ShopAiService
from apps.shop.services.domain_service import DomainService
from apps.shop.services.menu_file_import_service import MenuFileImportService
from apps.shop.services.menu_import_service import MenuImportService
from apps.shop.services.menu_service import MenuService
from apps.shop.services.notification_service import NotificationService
from apps.shop.services.order_service import ShopOrderService
from apps.shop.services.shop_service import ShopService
from apps.shop.services.storefront_service import StorefrontService
from core.authz.service import AuthzService
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.worktracker.access_service import WorkQueueAccessService
from core.worktracker.queue_access import WorkQueueAccessPort


@recipe
def work_queue_access(authz_service: AuthzService) -> WorkQueueAccessPort:
    return WorkQueueAccessService(authz_service)


class ShopDi(PlatformDi, recipes=(work_queue_access,)):
    settings: ShopSettings
    shop_service: ShopService
    menu_service: MenuService
    menu_import_service: MenuImportService
    menu_file_import_service: MenuFileImportService
    storefront_service: StorefrontService
    order_service: ShopOrderService
    notification_service: NotificationService
    domain_service: DomainService
    aggregate_service: AggregateService
    ai_service: ShopAiService


Di = Annotated[ShopDi, http_di(ShopDi), task_di(ShopDi)]
