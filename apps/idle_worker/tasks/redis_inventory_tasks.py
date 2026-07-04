"""Periodic Redis inventory metrics for Grafana."""

from __future__ import annotations

from apps.idle_worker.broker import broker as idle_broker
from core.redis_inventory.service import run_redis_inventory_tick

REDIS_INVENTORY_TASK_NAME = "redis_inventory_tick"


@idle_broker.task(task_name=REDIS_INVENTORY_TASK_NAME, queue_name="idle")
async def redis_inventory_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int | float | bool]:
    _ = schedule_task_id, company_id
    result = await run_redis_inventory_tick()
    return {
        "domain_dbsize": result.domain_db.dbsize,
        "broker_dbsize": result.broker_db.dbsize,
        "domain_no_ttl_total": result.domain_db.no_ttl_total,
        "broker_no_ttl_total": result.broker_db.no_ttl_total,
        "duration_ms": result.duration_ms,
    }
