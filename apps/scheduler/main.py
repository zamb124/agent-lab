"""FastAPI entrypoint для scheduler control-plane."""

import os

from core.config.testing import is_testing

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
CALENDAR_SYNC_MEETING_REMINDER_TASK_NAME = "calendar_sync_meeting_reminder_tick"
SPAN_BILLING_SETTLEMENT_TASK_NAME = "span_billing_settlement_tick"
PAYMENT_SYNC_TASK_NAME = "payment_sync_tick"
RAG_CLEANUP_EXPIRED_DOCUMENTS_TASK_NAME = "rag_cleanup_expired_documents_tick"
RAG_REEMBED_STALE_DOCUMENTS_TASK_NAME = "rag_reembed_stale_documents_tick"
CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME = "crm_reembed_stale_documents_tick"
SYSTEM_SCHEDULER_COMPANY_ID = "system"


async def _ensure_calendar_schedule(
    *,
    container,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
) -> None:
    if not config_enabled:
        logger.info("%s: disabled in config", log_label)
        return
    tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("%s schedule already exists, count=%s", log_label, len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await container.scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].id,
        )
        logger.info("%s schedule resumed: task_id=%s schedule_id=%s", log_label, resumed.id, resumed.schedule_id)
        return
    request = PlatformScheduleCreateRequest(
        target_service="flows",
        task_name=task_name,
        queue_name="idle",
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload={},
    )
    created = await container.scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info("%s schedule created: task_id=%s schedule_id=%s", log_label, created.id, created.schedule_id)


async def _ensure_rag_ttl_cleanup_schedule(
    *,
    container,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
) -> None:
    if not config_enabled:
        logger.info("%s: disabled in config", log_label)
        return
    tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("%s schedule already exists, count=%s", log_label, len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await container.scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].id,
        )
        logger.info("%s schedule resumed: task_id=%s schedule_id=%s", log_label, resumed.id, resumed.schedule_id)
        return
    request = PlatformScheduleCreateRequest(
        target_service="rag",
        task_name=task_name,
        queue_name="rag",
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload={},
    )
    created = await container.scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info("%s schedule created: task_id=%s schedule_id=%s", log_label, created.id, created.schedule_id)


async def _ensure_crm_reembed_schedule(
    *,
    container,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
) -> None:
    if not config_enabled:
        logger.info("%s: disabled in config", log_label)
        return
    tasks = await container.scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("%s schedule already exists, count=%s", log_label, len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await container.scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].id,
        )
        logger.info("%s schedule resumed: task_id=%s schedule_id=%s", log_label, resumed.id, resumed.schedule_id)
        return
    request = PlatformScheduleCreateRequest(
        target_service="crm",
        task_name=task_name,
        queue_name="crm",
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload={},
    )
    created = await container.scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info("%s schedule created: task_id=%s schedule_id=%s", log_label, created.id, created.schedule_id)


async def on_startup(app: FastAPI, container, settings: SchedulerSettings) -> None:
    if not is_testing():
        await ensure_system_company_exists(container)
    config = settings.calendar_sync
    await _ensure_calendar_schedule(
        container=container,
        config_enabled=config.enabled,
        task_name=CALENDAR_SYNC_TASK_NAME,
        cron=config.cron,
        log_label="Calendar sync",
    )
    await _ensure_calendar_schedule(
        container=container,
        config_enabled=config.sync_meeting_reminder_enabled,
        task_name=CALENDAR_SYNC_MEETING_REMINDER_TASK_NAME,
        cron=config.sync_meeting_reminder_cron,
        log_label="Calendar Sync meeting reminder",
    )
    billing_cfg = settings.billing.span_settlement
    await _ensure_calendar_schedule(
        container=container,
        config_enabled=billing_cfg.enabled,
        task_name=SPAN_BILLING_SETTLEMENT_TASK_NAME,
        cron=billing_cfg.cron,
        log_label="Span billing settlement",
    )
    payment_cfg = settings.payment_providers
    await _ensure_calendar_schedule(
        container=container,
        config_enabled=payment_cfg.sync_enabled,
        task_name=PAYMENT_SYNC_TASK_NAME,
        cron=payment_cfg.sync_cron,
        log_label="Payment sync",
    )
    cfg = settings.rag.ttl
    await _ensure_rag_ttl_cleanup_schedule(
        container=container,
        config_enabled=cfg.cleanup_enabled,
        task_name=RAG_CLEANUP_EXPIRED_DOCUMENTS_TASK_NAME,
        cron=cfg.cleanup_cron,
        log_label="RAG TTL cleanup",
    )
    await _ensure_rag_ttl_cleanup_schedule(
        container=container,
        config_enabled=cfg.reembed_enabled,
        task_name=RAG_REEMBED_STALE_DOCUMENTS_TASK_NAME,
        cron=cfg.reembed_cron,
        log_label="RAG reembed stale",
    )
    await _ensure_crm_reembed_schedule(
        container=container,
        config_enabled=cfg.reembed_enabled,
        task_name=CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
        cron=cfg.reembed_cron,
        log_label="CRM reembed stale",
    )


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
    documentation_gateway_prefix="scheduler",
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
