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
    STOCK_PUTAWAY_SHADOW_RECORD,
    STOCK_RECONCILE_TICK,
    STOCK_REORDER_TICK,
    STOCK_TRANSFER_COMMAND_RESUME,
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


@platform_task(STOCK_TRANSFER_COMMAND_RESUME)
async def stock_transfer_command_resume(
    *,
    company_id: str,
    transfer_id: str,
    command: str,
    idempotency_key: str,
    actor_user_id: str,
    create_backorder: bool = True,
    di: Di,
) -> JsonObject:
    """Повторный прогон команды накладной после webhook putaway-решения.

    ``A2ACallPending`` из ``resolve_putaway`` припарковал исходную команду;
    здесь тот же метод движка идёт повторно — ``_call_flow`` берёт сохранённый
    результат по ``dedup_key`` без повторного submit'а.
    """
    await _enter_worker_context(trace_id=f"stock:resume:{transfer_id}")
    try:
        engine = di.move_engine
        if command == "confirm":
            transfer = await engine.confirm_transfer(
                company_id=company_id,
                transfer_id=transfer_id,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
            )
        elif command == "assign":
            transfer = await engine.assign_transfer(
                company_id=company_id,
                transfer_id=transfer_id,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
            )
        else:
            transfer = await engine.validate_transfer(
                company_id=company_id,
                transfer_id=transfer_id,
                idempotency_key=idempotency_key,
                actor_user_id=actor_user_id,
                create_backorder=create_backorder,
            )
        return {"transfer_id": transfer.transfer_id, "state": transfer.state.value}
    finally:
        clear_context()


@platform_task(STOCK_PUTAWAY_SHADOW_RECORD)
async def stock_putaway_shadow_record(
    *,
    a2a_task_id: str,
    a2a_state: str,
    a2a_payload: JsonObject,
    a2a_base_url: str,
    company_id: str,
    warehouse_id: str,
    operation_type_id: str,
    move_id: str,
    transfer_id: str,
    flow_id: str,
    candidate_location_ids: list[str],
    actor_user_id: str,
    resume_task: str | None = None,
    resume_kwargs: JsonObject | None = None,
    di: Di,
) -> JsonObject:
    """Записать теневое putaway-предложение flow в ``stock_decisions``.

    SHADOW-режим не блокирует команду: решение доезжает асинхронно webhook'ом
    и пишется аудит-строкой (SUGGESTED с выбором / REJECTED на терминальном
    сбое) — леджер она не трогает. ``resume_*`` — наследие resume-контекста
    вызывающей команды, shadow-continuation их не использует.
    """
    _ = a2a_payload, resume_task, resume_kwargs
    await _enter_worker_context(trace_id=f"stock:shadow:{move_id}")
    try:
        decision = await di.placement_service.record_shadow_decision(
            company_id=company_id,
            warehouse_id=warehouse_id,
            operation_type_id=operation_type_id,
            move_id=move_id,
            transfer_id=transfer_id,
            flow_id=flow_id,
            candidate_location_ids=candidate_location_ids,
            a2a_task_id=a2a_task_id,
            a2a_state=a2a_state,
            a2a_base_url=a2a_base_url,
            actor_user_id=actor_user_id,
        )
        return {"decision_id": decision.decision_id, "status": decision.status.value}
    finally:
        clear_context()


__all__ = [
    "stock_claims_gc_tick",
    "stock_lane_gc_tick",
    "stock_lane_relay_tick",
    "stock_cycle_count_tick",
    "stock_putaway_shadow_record",
    "stock_reconcile_tick",
    "stock_reorder_tick",
    "stock_transfer_command_resume",
]
