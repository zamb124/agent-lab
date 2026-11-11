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
STOCK_TRANSFER_COMMAND_RESUME = declare_task(
    "stock_transfer_command_resume", queue="stock", retry=True, max_retries=2
)
STOCK_PUTAWAY_SHADOW_RECORD = declare_task(
    "stock_putaway_shadow_record", queue="stock", retry=True, max_retries=2
)

__all__ = [
    "STOCK_CLAIMS_GC_TICK",
    "STOCK_CYCLE_COUNT_TICK",
    "STOCK_LANE_GC_TICK",
    "STOCK_LANE_RELAY_TICK",
    "STOCK_PUTAWAY_SHADOW_RECORD",
    "STOCK_RECONCILE_TICK",
    "STOCK_REORDER_TICK",
    "STOCK_TRANSFER_COMMAND_RESUME",
]
