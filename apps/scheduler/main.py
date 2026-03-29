"""FastAPI entrypoint для scheduler control-plane."""

import os

from fastapi import FastAPI

from apps.scheduler.api.v1 import api_v1_router
from apps.scheduler.config import SchedulerSettings, get_scheduler_settings
from apps.scheduler.container import get_scheduler_container
from core.app import create_service_app
from core.identity.system_bootstrap import ensure_system_company_exists
from core.logging import get_logger
from core.scheduler.models import (
    PlatformScheduleCreateRequest,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)

logger = get_logger(__name__)

CALENDAR_SYNC_TASK_NAME = "calendar_sync_tick"
SYSTEM_SCHEDULER_COMPANY_ID = "system"


async def on_startup(app: FastAPI, container, settings: SchedulerSettings) -> None:
    if os.getenv("TESTING") != "true":
        await ensure_system_company_exists(container)
    config = settings.calendar_sync
    if not config.enabled:
        logger.info("Calendar scheduler sync is disabled")
        return
    tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=CALENDAR_SYNC_TASK_NAME,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("Calendar sync schedule already exists, count=%s", len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await container.scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].id,
        )
        logger.info("Calendar sync schedule resumed: task_id=%s schedule_id=%s", resumed.id, resumed.schedule_id)
        return
    request = PlatformScheduleCreateRequest(
        target_service="flows",
        task_name=CALENDAR_SYNC_TASK_NAME,
        schedule_type=PlatformScheduleType.CRON,
        cron=config.cron,
        timezone="UTC",
        payload={},
    )
    created = await container.scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info("Calendar sync schedule created: task_id=%s schedule_id=%s", created.id, created.schedule_id)


async def on_shutdown(app: FastAPI, container) -> None:
    return None


app = create_service_app(
    service_name="scheduler",
    settings_class=SchedulerSettings,
    get_container=get_scheduler_container,
    routers=[api_v1_router],
    repository_names=[],
    on_startup=on_startup,
    on_shutdown=on_shutdown,
    cors_origins=["*"],
    title="Platform Scheduler",
    description="Единый cron/control-plane для всех сервисов",
    version="1.0.0",
    api_version="v1",
    include_crud_routers=False,
    mkdocs_gateway_prefix="scheduler",
)


if __name__ == "__main__":
    import uvicorn

    settings = get_scheduler_settings()
    uvicorn.run(
        "apps.scheduler.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
    )
