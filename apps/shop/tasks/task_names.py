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
SHOP_NOTIFY_CUSTOMER = declare_task(
    "shop_notify_customer", queue="shop", retry=True, max_retries=3
)
SHOP_NOTIFY_BACK_IN_STOCK = declare_task(
    "shop_notify_back_in_stock", queue="shop", retry=True, max_retries=3
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
SHOP_AI_DESCRIBE_BATCH = declare_task(
    "shop_ai_describe_batch", queue="shop"
)
SHOP_AI_CALL = declare_task("shop_ai_call", queue="shop")
SHOP_SEED_DEMO_COMPANY = declare_task(
    "shop_seed_demo_company", queue="shop", retry=True, max_retries=2
)

__all__ = [
    "SHOP_AI_CALL",
    "SHOP_AI_DESCRIBE_BATCH",
    "SHOP_NOTIFY_BACK_IN_STOCK",
    "SHOP_NOTIFY_CUSTOMER",
    "SHOP_NOTIFY_ORDER",
    "SHOP_PROVISION_DOMAIN",
    "SHOP_REBUILD_AGGREGATE",
    "SHOP_REBUILD_STOREFRONT",
    "SHOP_RECONCILE_DOMAINS_TICK",
    "SHOP_SEED_DEMO_COMPANY",
]
