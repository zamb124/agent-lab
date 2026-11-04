"""Declaration-модуль shop задач (очередь ``shop``).

Лёгкий: только объявления. Импортируется producer'ами (``enqueue``)
и impl-модулями (``@platform_task``).
"""

from core.tasks import declare_task

SHOP_REBUILD_STOREFRONT = declare_task(
    "shop_rebuild_storefront", queue="shop", retry=True, max_retries=2
)
SHOP_NOTIFY_ORDER = declare_task(
    "shop_notify_order", queue="shop", retry=True, max_retries=3
)
SHOP_PROVISION_DOMAIN = declare_task(
    "shop_provision_domain", queue="shop", retry=True, max_retries=1
)
SHOP_RECONCILE_DOMAINS_TICK = declare_task(
    "shop_reconcile_domains_tick", queue="shop", scheduled=True, retry=True, max_retries=1
)
SHOP_REBUILD_AGGREGATE = declare_task(
    "shop_rebuild_aggregate", queue="shop", retry=True, max_retries=2
)
SHOP_MENU_PHOTO_DOWNLOAD = declare_task("shop_menu_photo_download", queue="shop")

__all__ = [
    "SHOP_MENU_PHOTO_DOWNLOAD",
    "SHOP_NOTIFY_ORDER",
    "SHOP_PROVISION_DOMAIN",
    "SHOP_REBUILD_AGGREGATE",
    "SHOP_REBUILD_STOREFRONT",
    "SHOP_RECONCILE_DOMAINS_TICK",
]
