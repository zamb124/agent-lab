"""Declaration-модуль stock задач (очередь ``stock``).

Лёгкий: только объявления. Импортируется producer'ами (``enqueue``)
и impl-модулями (``@platform_task``).
"""

from core.tasks import declare_task

STOCK_RECONCILE_TICK = declare_task(
    "stock_reconcile_tick", queue="stock", scheduled=True, retry=True, max_retries=1
)
STOCK_CLAIMS_GC_TICK = declare_task(
    "stock_claims_gc_tick", queue="stock", scheduled=True, retry=True, max_retries=1
)
STOCK_REORDER_TICK = declare_task(
    "stock_reorder_tick", queue="stock", scheduled=True, retry=True, max_retries=1
)
STOCK_CYCLE_COUNT_TICK = declare_task(
    "stock_cycle_count_tick", queue="stock", scheduled=True, retry=True, max_retries=1
)
STOCK_LANE_RELAY_TICK = declare_task(
    "stock_lane_relay_tick", queue="stock", scheduled=True, retry=True, max_retries=2
)
STOCK_LANE_GC_TICK = declare_task(
    "stock_lane_gc_tick", queue="stock", scheduled=True, retry=True, max_retries=1
)

__all__ = [
    "STOCK_CLAIMS_GC_TICK",
    "STOCK_CYCLE_COUNT_TICK",
    "STOCK_LANE_GC_TICK",
    "STOCK_LANE_RELAY_TICK",
    "STOCK_RECONCILE_TICK",
    "STOCK_REORDER_TICK",
]
