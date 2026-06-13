"""Idempotent crawl cron schedules in platform scheduler."""

from __future__ import annotations

from apps.scheduler.container import SchedulerContainer
from apps.search_worker.tasks.task_names import (
    CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
    CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
)
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)

logger = get_logger(__name__)

SYSTEM_SCHEDULER_COMPANY_ID = "system"
CRAWL_ORCHESTRATOR_TICK_CRON = "0 */6 * * *"
CRAWL_RECLAIM_STALE_FETCHING_CRON = "*/15 * * * *"
CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID = "runet_platform"


async def ensure_search_crawl_schedules(*, container: SchedulerContainer) -> None:
    orchestrator_tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
            limit=200,
            offset=0,
        ),
    )
    pending_orchestrator = [
        task
        for task in orchestrator_tasks
        if task.status == ScheduledTaskStatus.PENDING
        and task.payload.get("crawl_profile_id") == CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID
    ]
    if pending_orchestrator:
        logger.info(
            "Search crawl orchestrator schedule already exists, count=%s",
            len(pending_orchestrator),
        )
    else:
        paused_orchestrator = [
            task
            for task in orchestrator_tasks
            if task.status == ScheduledTaskStatus.PAUSED
            and task.payload.get("crawl_profile_id") == CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID
        ]
        if paused_orchestrator:
            resumed = await container.scheduler_service.resume(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                schedule_task_id=paused_orchestrator[0].schedule_task_id,
            )
            logger.info(
                "Search crawl orchestrator schedule resumed: schedule_task_id=%s schedule_id=%s",
                resumed.schedule_task_id,
                resumed.schedule_id,
            )
        else:
            created = await container.scheduler_service.create(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                user_id=None,
                request=PlatformScheduleCreateRequest(
                    target_service="search",
                    task_name=CRAWL_ORCHESTRATOR_TICK_TASK_NAME,
                    queue_name="search",
                    schedule_type=PlatformScheduleType.CRON,
                    cron=CRAWL_ORCHESTRATOR_TICK_CRON,
                    timezone="UTC",
                    payload={"crawl_profile_id": CRAWL_ORCHESTRATOR_DEFAULT_PROFILE_ID},
                ),
            )
            logger.info(
                "Search crawl orchestrator schedule created: schedule_task_id=%s schedule_id=%s",
                created.schedule_task_id,
                created.schedule_id,
            )

    reclaim_tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
            limit=200,
            offset=0,
        ),
    )
    pending_reclaim = [task for task in reclaim_tasks if task.status == ScheduledTaskStatus.PENDING]
    if pending_reclaim:
        logger.info(
            "Search crawl reclaim schedule already exists, count=%s",
            len(pending_reclaim),
        )
    else:
        paused_reclaim = [task for task in reclaim_tasks if task.status == ScheduledTaskStatus.PAUSED]
        if paused_reclaim:
            resumed = await container.scheduler_service.resume(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                schedule_task_id=paused_reclaim[0].schedule_task_id,
            )
            logger.info(
                "Search crawl reclaim schedule resumed: schedule_task_id=%s schedule_id=%s",
                resumed.schedule_task_id,
                resumed.schedule_id,
            )
        else:
            created = await container.scheduler_service.create(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                user_id=None,
                request=PlatformScheduleCreateRequest(
                    target_service="search",
                    task_name=CRAWL_RECLAIM_STALE_FETCHING_TASK_NAME,
                    queue_name="search",
                    schedule_type=PlatformScheduleType.CRON,
                    cron=CRAWL_RECLAIM_STALE_FETCHING_CRON,
                    timezone="UTC",
                    payload={},
                ),
            )
            logger.info(
                "Search crawl reclaim schedule created: schedule_task_id=%s schedule_id=%s",
                created.schedule_task_id,
                created.schedule_id,
            )
