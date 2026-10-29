"""Stock TaskIQ tasks — фоновые тики склада (очередь ``stock``).

Каждый тик — «уборка ночной смены»: сверка остатков, возврат
брошенных заданий, пополнение по min/max, плановый пересчёт ячеек.
Сами правки идут в полосах складов через MaintenanceService —
тик не может пересечься с рабочей проводкой.
"""

from __future__ import annotations

from apps.stock.di import Di
from apps.stock.tasks.task_names import (
    STOCK_CLAIMS_GC_TICK,
    STOCK_CYCLE_COUNT_TICK,
    STOCK_LANE_GC_TICK,
    STOCK_LANE_RELAY_TICK,
    STOCK_RECONCILE_TICK,
    STOCK_REORDER_TICK,
)
from core.context import clear_context, set_context
from core.identity.system_bootstrap import build_system_admin_job_context
from core.tasks import platform_task
from core.types import JsonObject


async def _enter_worker_context(*, trace_id: str) -> None:
    _ = set_context(
        await build_system_admin_job_context(
            trace_id=trace_id,
            session_id=f"stock:{trace_id}",
            channel="stock",
        )
    )


@platform_task(STOCK_RECONCILE_TICK)
async def stock_reconcile_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Сверка леджера: резервы quant vs открытые строки, застрявшие move."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:reconcile")
    try:
        stats = await di.maintenance_service.reconcile_tick()
        return JsonObject(stats)
    finally:
        clear_context()


@platform_task(STOCK_CLAIMS_GC_TICK)
async def stock_claims_gc_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Отпустить брошенные захваты заданий (claimed и не двигалось)."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:claims_gc")
    try:
        stats = await di.maintenance_service.claims_gc_tick()
        return JsonObject(stats)
    finally:
        clear_context()


@platform_task(STOCK_REORDER_TICK)
async def stock_reorder_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Min/max пополнение: остаток ниже min → черновик пополнения до max."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:reorder")
    try:
        stats = await di.maintenance_service.reorder_tick()
        return JsonObject(stats)
    finally:
        clear_context()


@platform_task(STOCK_CYCLE_COUNT_TICK)
async def stock_cycle_count_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Плановый пересчёт: просроченные по last_count_at ячейки → задания count."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:cycle_count")
    try:
        stats = await di.maintenance_service.cycle_count_tick()
        return JsonObject(stats)
    finally:
        clear_context()


@platform_task(STOCK_LANE_RELAY_TICK)
async def stock_lane_relay_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Догнать lane-коммиты, чей push не дошёл до шины событий."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:lane_relay")
    try:
        stats = await di.maintenance_service.relay_tick()
        return JsonObject(stats)
    finally:
        clear_context()


@platform_task(STOCK_LANE_GC_TICK)
async def stock_lane_gc_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> JsonObject:
    """Вымести опубликованные lane-коммиты за окном идемпотентности."""
    _ = (schedule_task_id, company_id)
    await _enter_worker_context(trace_id="stock:lane_gc")
    try:
        stats = await di.maintenance_service.lane_gc_tick()
        return JsonObject(stats)
    finally:
        clear_context()


__all__ = [
    "stock_claims_gc_tick",
    "stock_lane_gc_tick",
    "stock_lane_relay_tick",
    "stock_cycle_count_tick",
    "stock_reconcile_tick",
    "stock_reorder_tick",
]
