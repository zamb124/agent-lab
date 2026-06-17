"""Idempotent crawl cron schedules in platform scheduler."""

from __future__ import annotations

from collections.abc import Callable

from apps.scheduler.container import SchedulerContainer
from apps.search_worker.tasks.task_names import (
    CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
    CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
)
from core.logging import get_logger
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.types import JsonObject

logger = get_logger(__name__)

SYSTEM_SCHEDULER_COMPANY_ID = "system"
CRAWL_ORCHESTRATOR_TICK_CRON = "*/10 * * * *"
CRAWL_RECLAIM_STALE_FETCHING_CRON = "*/15 * * * *"
CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID = "runet_platform"


def _canonical_crawl_task_payload(schedule_task_id: str, payload: JsonObject) -> JsonObject:
    canonical_payload = dict(payload)
    canonical_payload["schedule_task_id"] = schedule_task_id
    canonical_payload["company_id"] = SYSTEM_SCHEDULER_COMPANY_ID
    return canonical_payload


def _is_redis_cron_snapshot_current(
    snapshot: PlatformRedisScheduleSnapshot,
    *,
    task_name: str,
    cron: str,
    expected_payload: JsonObject,
) -> bool:
    return (
        snapshot.exists_in_redis
        and snapshot.task_name == task_name
        and snapshot.cron == cron
        and snapshot.kwargs == expected_payload
    )


async def _reconcile_crawl_cron_schedule(
    *,
    container: SchedulerContainer,
    task: PlatformScheduledTask,
    task_name: str,
    cron: str,
    payload: JsonObject,
    log_label: str,
) -> PlatformScheduledTask:
    expected_payload = _canonical_crawl_task_payload(task.schedule_task_id, payload)
    recreate_schedule = False
    if task.status == ScheduledTaskStatus.PENDING:
        snapshot = await container.scheduler_service.get_redis_snapshot(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=task.schedule_task_id,
        )
        recreate_schedule = not _is_redis_cron_snapshot_current(
            snapshot,
            task_name=task_name,
            cron=cron,
            expected_payload=expected_payload,
        )
    if task.payload == expected_payload and not recreate_schedule:
        return task

    repaired = await container.scheduler_service.reconcile_payload(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_task_id=task.schedule_task_id,
        payload=payload,
        recreate_schedule=recreate_schedule,
    )
    logger.warning(
        "%s cron schedule reconciled: schedule_task_id=%s recreate_schedule=%s",
        log_label,
        repaired.schedule_task_id,
        recreate_schedule,
    )
    return repaired


def _match_all_crawl_schedules(_task: PlatformScheduledTask) -> bool:
    return True


async def _ensure_crawl_cron_schedule(
    *,
    container: SchedulerContainer,
    task_name: str,
    cron: str,
    payload: JsonObject,
    log_label: str,
    pending_match: Callable[[PlatformScheduledTask], bool] | None = None,
) -> None:
    tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    match_task = pending_match if pending_match is not None else _match_all_crawl_schedules
    pending_tasks = [
        task
        for task in tasks
        if task.status == ScheduledTaskStatus.PENDING and match_task(task)
    ]
    if pending_tasks:
        logger.info("%s schedule already exists, count=%s", log_label, len(pending_tasks))
        _ = await _reconcile_crawl_cron_schedule(
            container=container,
            task=pending_tasks[0],
            task_name=task_name,
            cron=cron,
            payload=payload,
            log_label=log_label,
        )
        return

    paused_tasks = [
        task
        for task in tasks
        if task.status == ScheduledTaskStatus.PAUSED and match_task(task)
    ]
    if paused_tasks:
        resumed = await container.scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].schedule_task_id,
        )
        logger.info(
            "%s schedule resumed: schedule_task_id=%s schedule_id=%s",
            log_label,
            resumed.schedule_task_id,
            resumed.schedule_id,
        )
        _ = await _reconcile_crawl_cron_schedule(
            container=container,
            task=resumed,
            task_name=task_name,
            cron=cron,
            payload=payload,
            log_label=log_label,
        )
        return

    created = await container.scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=PlatformScheduleCreateRequest(
            target_service="search",
            task_name=task_name,
            queue_name="search",
            schedule_type=PlatformScheduleType.CRON,
            cron=cron,
            timezone="UTC",
            payload=dict(payload),
        ),
    )
    logger.info(
        "%s schedule created: schedule_task_id=%s schedule_id=%s",
        log_label,
        created.schedule_task_id,
        created.schedule_id,
    )


async def ensure_search_crawl_schedules(*, container: SchedulerContainer) -> None:
    await _ensure_crawl_cron_schedule(
        container=container,
        task_name=CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
        cron=CRAWL_ORCHESTRATOR_TICK_CRON,
        payload={"crawl_profile_id": CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID},
        log_label="Search crawl orchestrator",
        pending_match=lambda task: (
            task.payload.get("crawl_profile_id") == CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID
        ),
    )
    await _ensure_crawl_cron_schedule(
        container=container,
        task_name=CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
        cron=CRAWL_RECLAIM_STALE_FETCHING_CRON,
        payload={},
        log_label="Search crawl reclaim",
    )
