"""FastAPI entrypoint для scheduler control-plane."""

from datetime import datetime, timezone

from apps.crm.tasks.task_names import (
    CRM_RECONCILE_DAILY_SUMMARY,
    CRM_REEMBED_STALE_DOCUMENTS,
)
from apps.flows.src.tasks.task_names import (
    TASK_MCP_CATALOG_CRAWL,
    TASK_MCP_CATALOG_RESYNC_TOOLS,
    TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK,
)
from apps.geo.tasks.task_names import GEO_OSM_SYNC_TICK, GEO_TILES_SYNC
from apps.idle.tasks.task_names import (
    TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK,
    TASK_CALENDAR_SYNC_TICK,
    TASK_FILE_RETENTION_BACKFILL_TICK,
    TASK_FILE_RETENTION_PURGE_TICK,
    TASK_PAYMENT_SYNC_TICK,
    TASK_PLATFORM_SCHEDULES_GC_TICK,
    TASK_REDIS_INVENTORY_TICK,
    TASK_SPAN_BILLING_SETTLEMENT_TICK,
)
from apps.rag.tasks.task_names import (
    RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK,
    RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK,
    RAG_REEMBED_STALE_DOCUMENTS_TICK,
)
from apps.scheduler.api.v1 import api_v1_router
from apps.scheduler.config import SchedulerSettings, get_scheduler_settings
from apps.scheduler.crawl_schedule_bootstrap import ensure_search_crawl_schedules
from apps.scheduler.di import SchedulerDi
from apps.scheduler.realtime.command_router import SCHEDULER_OPERATIONS
from apps.stock.tasks.task_names import (
    STOCK_CLAIMS_GC_TICK,
    STOCK_CYCLE_COUNT_TICK,
    STOCK_LANE_GC_TICK,
    STOCK_LANE_RELAY_TICK,
    STOCK_RECONCILE_TICK,
    STOCK_REORDER_TICK,
)
from core.ai.task_names import TASK_REFRESH_PLATFORM_FREE_MODELS, TASK_SYNC_LLM_MODELS
from core.app import create_service_app
from core.config.testing import is_testing
from core.customers.task_names import CUSTOMER_AUTH_TG_POLL
from core.di import recipe
from core.identity.system_bootstrap import (
    ensure_system_company_exists,
)
from core.logging import get_logger
from core.mail.task_names import MAIL_IDLE_SUPERVISOR, MAIL_SYNC_TICK
from core.scheduler import SchedulerService
from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    ScheduledTaskStatus,
)
from core.tasks import get_task_spec
from core.types import JsonObject

logger = get_logger(__name__)

CRM_RECONCILE_DAILY_SUMMARY_CRON = "0 * * * *"
TOOL_TAG_GROUPS_DESCRIBE_CRON = "0 3 * * *"
SYSTEM_SCHEDULER_COMPANY_ID = "system"
LLM_MODELS_SYNC_PAYLOAD_MARKER = "llm_models_background_sync"
PLATFORM_FREE_MODELS_SYNC_PAYLOAD_MARKER = "platform_free_models_background_sync"


def _canonical_system_payload(schedule_task_id: str, payload: JsonObject) -> JsonObject:
    canonical_payload = dict(payload)
    canonical_payload["schedule_task_id"] = schedule_task_id
    canonical_payload["company_id"] = SYSTEM_SCHEDULER_COMPANY_ID
    return canonical_payload


def _is_redis_interval_snapshot_current(
    snapshot: PlatformRedisScheduleSnapshot,
    *,
    task_name: str,
    interval_seconds: int,
    expected_payload: JsonObject,
) -> bool:
    return (
        snapshot.exists_in_redis
        and snapshot.task_name == task_name
        and snapshot.interval_seconds == interval_seconds
        and snapshot.kwargs == expected_payload
    )


async def _reconcile_idle_interval_payload(
    *,
    scheduler_service: SchedulerService,
    task: PlatformScheduledTask,
    task_name: str,
    interval_seconds: int,
    payload: JsonObject,
    log_label: str,
) -> PlatformScheduledTask:
    expected_payload = _canonical_system_payload(task.schedule_task_id, payload)
    recreate_schedule = False
    if task.status == ScheduledTaskStatus.PENDING:
        snapshot = await scheduler_service.get_redis_snapshot(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=task.schedule_task_id,
        )
        recreate_schedule = not _is_redis_interval_snapshot_current(
            snapshot,
            task_name=task_name,
            interval_seconds=interval_seconds,
            expected_payload=expected_payload,
        )
    if task.payload == expected_payload and not recreate_schedule:
        return task

    repaired = await scheduler_service.reconcile_payload(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_task_id=task.schedule_task_id,
        payload=payload,
        recreate_schedule=recreate_schedule,
    )
    logger.warning(
        "scheduler.interval.schedule.reconciled.schedule_task_id.recreate_schedule",
        log_label=log_label,
        schedule_task_id=repaired.schedule_task_id,
        recreate_schedule=recreate_schedule,
    )
    return repaired


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


async def _reconcile_cron_payload(
    *,
    scheduler_service: SchedulerService,
    task: PlatformScheduledTask,
    task_name: str,
    cron: str,
    log_label: str,
) -> PlatformScheduledTask:
    expected_payload = _canonical_system_payload(task.schedule_task_id, {})
    recreate_schedule = False
    if task.status == ScheduledTaskStatus.PENDING:
        snapshot = await scheduler_service.get_redis_snapshot(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=task.schedule_task_id,
        )
        recreate_schedule = not _is_redis_cron_snapshot_current(
            snapshot,
            task_name=task_name,
            cron=cron,
            expected_payload=expected_payload,
        )
    if (
        task.cron == cron
        and task.payload == expected_payload
        and not recreate_schedule
    ):
        return task

    repaired = await scheduler_service.reconcile_cron(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        schedule_task_id=task.schedule_task_id,
        cron=cron,
        payload={},
        recreate_schedule=recreate_schedule,
    )
    logger.warning(
        "scheduler.cron.schedule.reconciled.schedule_task_id.recreate_schedule",
        log_label=log_label,
        schedule_task_id=repaired.schedule_task_id,
        recreate_schedule=recreate_schedule,
        cron=cron,
    )
    return repaired


async def _ensure_calendar_schedule(
    *,
    scheduler_service: SchedulerService,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
    run_now_on_start: bool = False,
) -> None:
    if not config_enabled:
        logger.info("scheduler.disabled.config", log_label=log_label)
        return
    tasks = await scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    task: PlatformScheduledTask | None = None
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("scheduler.schedule.exists.count", log_label=log_label, count=len(pending_tasks))
        task = await _reconcile_cron_payload(
            scheduler_service=scheduler_service,
            task=pending_tasks[0],
            task_name=task_name,
            cron=cron,
            log_label=log_label,
        )
    else:
        paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
        if len(paused_tasks) > 0:
            resumed = await scheduler_service.resume(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                schedule_task_id=paused_tasks[0].schedule_task_id,
            )
            logger.info(
                "scheduler.schedule.resumed.schedule_task_id.schedule_id",
                log_label=log_label,
                schedule_task_id=resumed.schedule_task_id,
                schedule_id=resumed.schedule_id,
            )
            task = await _reconcile_cron_payload(
                scheduler_service=scheduler_service,
                task=resumed,
                task_name=task_name,
                cron=cron,
                log_label=log_label,
            )
        else:
            request = PlatformScheduleCreateRequest(
                target_service="flows",
                task_name=task_name,
                queue_name="idle",
                schedule_type=PlatformScheduleType.CRON,
                cron=cron,
                timezone="UTC",
                payload={},
            )
            task = await scheduler_service.create(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                user_id=None,
                request=request,
            )
            logger.info(
                "scheduler.schedule.created.schedule_task_id.schedule_id",
                log_label=log_label,
                schedule_task_id=task.schedule_task_id,
                schedule_id=task.schedule_id,
            )
    if run_now_on_start:
        _ = await scheduler_service.run_now(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=task.schedule_task_id,
        )
        logger.info("scheduler.cron.schedule.kicked.immediately.schedule_task_id", log_label=log_label, schedule_task_id=task.schedule_task_id)


async def _ensure_idle_interval_schedule(
    *,
    scheduler_service: SchedulerService,
    config_enabled: bool,
    task_name: str,
    interval_seconds: int,
    payload: JsonObject,
    log_label: str,
    run_now_on_start: bool = False,
) -> None:
    if not config_enabled:
        logger.info("scheduler.disabled.config", log_label=log_label)
        return
    tasks = await scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    compatible_tasks = [
        task
        for task in tasks
        if task.schedule_type == PlatformScheduleType.INTERVAL
        and task.interval_seconds == interval_seconds
    ]
    incompatible_pending = [
        task
        for task in tasks
        if task.status == ScheduledTaskStatus.PENDING and task not in compatible_tasks
    ]
    if incompatible_pending:
        logger.warning(
            "scheduler.incompatible.pending.schedules.leaving.them",
            log_label=log_label,
            value_1=[task.schedule_task_id for task in incompatible_pending],
        )
    pending_tasks = [task for task in compatible_tasks if task.status == ScheduledTaskStatus.PENDING]
    if pending_tasks:
        task = pending_tasks[0]
        logger.info("scheduler.interval.schedule.exists.count", log_label=log_label, count=len(pending_tasks))
    else:
        paused_tasks = [task for task in compatible_tasks if task.status == ScheduledTaskStatus.PAUSED]
        if paused_tasks:
            task = await scheduler_service.resume(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                schedule_task_id=paused_tasks[0].schedule_task_id,
            )
            logger.info(
                "scheduler.interval.schedule.resumed.schedule_task_id.schedule_id",
                log_label=log_label,
                schedule_task_id=task.schedule_task_id,
                schedule_id=task.schedule_id,
            )
        else:
            request = PlatformScheduleCreateRequest(
                target_service="flows",
                task_name=task_name,
                queue_name="idle",
                schedule_type=PlatformScheduleType.INTERVAL,
                interval_seconds=interval_seconds,
                timezone="UTC",
                payload=dict(payload),
                run_at=datetime.now(timezone.utc),
            )
            task = await scheduler_service.create(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                user_id=None,
                request=request,
            )
            logger.info(
                "scheduler.interval.schedule.created.schedule_task_id.schedule_id",
                log_label=log_label,
                schedule_task_id=task.schedule_task_id,
                schedule_id=task.schedule_id,
            )
    task = await _reconcile_idle_interval_payload(
        scheduler_service=scheduler_service,
        task=task,
        task_name=task_name,
        interval_seconds=interval_seconds,
        payload=payload,
        log_label=log_label,
    )
    if run_now_on_start:
        _ = await scheduler_service.run_now(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=task.schedule_task_id,
        )
        logger.info("scheduler.interval.schedule.kicked.immediately.schedule_task_id", log_label=log_label, schedule_task_id=task.schedule_task_id)


async def _ensure_stock_interval_schedule(
    *,
    scheduler_service: SchedulerService,
    config_enabled: bool,
    task_name: str,
    interval_seconds: int,
    log_label: str,
) -> None:
    """Интервальный тик stock-очереди — как idle-вариант, но в свою очередь."""
    if not config_enabled:
        logger.info("scheduler.disabled.config", log_label=log_label)
        return
    tasks = await scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    compatible_tasks = [
        task
        for task in tasks
        if task.schedule_type == PlatformScheduleType.INTERVAL
        and task.interval_seconds == interval_seconds
    ]
    payload: JsonObject = {}
    pending_tasks = [task for task in compatible_tasks if task.status == ScheduledTaskStatus.PENDING]
    task: PlatformScheduledTask
    if pending_tasks:
        task = pending_tasks[0]
        logger.info("scheduler.stock.schedule.exists.count", log_label=log_label, count=len(pending_tasks))
    else:
        paused_tasks = [task for task in compatible_tasks if task.status == ScheduledTaskStatus.PAUSED]
        if paused_tasks:
            task = await scheduler_service.resume(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                schedule_task_id=paused_tasks[0].schedule_task_id,
            )
        else:
            request = PlatformScheduleCreateRequest(
                target_service="stock",
                task_name=task_name,
                queue_name=get_task_spec(task_name).queue,
                schedule_type=PlatformScheduleType.INTERVAL,
                interval_seconds=interval_seconds,
                timezone="UTC",
                payload={},
                run_at=datetime.now(timezone.utc),
            )
            task = await scheduler_service.create(
                company_id=SYSTEM_SCHEDULER_COMPANY_ID,
                user_id=None,
                request=request,
            )
            logger.info(
                "scheduler.stock.schedule.created.schedule_task_id.schedule_id",
                log_label=log_label,
                schedule_task_id=task.schedule_task_id,
                schedule_id=task.schedule_id,
            )
    _ = await _reconcile_idle_interval_payload(
        scheduler_service=scheduler_service,
        task=task,
        task_name=task_name,
        interval_seconds=interval_seconds,
        payload=payload,
        log_label=log_label,
    )


async def _ensure_rag_ttl_cleanup_schedule(
    *,
    scheduler_service: SchedulerService,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
) -> None:
    if not config_enabled:
        logger.info("scheduler.disabled.config", log_label=log_label)
        return
    tasks = await scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("scheduler.schedule.exists.count", log_label=log_label, count=len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].schedule_task_id,
        )
        logger.info(
            "scheduler.schedule.resumed.schedule_task_id.schedule_id",
            log_label=log_label,
            schedule_task_id=resumed.schedule_task_id,
            schedule_id=resumed.schedule_id,
        )
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
    created = await scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info(
        "scheduler.schedule.created.schedule_task_id.schedule_id",
        log_label=log_label,
        schedule_task_id=created.schedule_task_id,
        schedule_id=created.schedule_id,
    )


async def _ensure_crm_cron_schedule(
    *,
    scheduler_service: SchedulerService,
    config_enabled: bool,
    task_name: str,
    cron: str,
    log_label: str,
) -> None:
    if not config_enabled:
        logger.info("scheduler.disabled.config", log_label=log_label)
        return
    tasks = await scheduler_service.list(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        filters=PlatformScheduleFilter(
            task_name=task_name,
            limit=200,
            offset=0,
        ),
    )
    pending_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PENDING]
    if len(pending_tasks) > 0:
        logger.info("scheduler.schedule.exists.count", log_label=log_label, count=len(pending_tasks))
        return
    paused_tasks = [task for task in tasks if task.status == ScheduledTaskStatus.PAUSED]
    if len(paused_tasks) > 0:
        resumed = await scheduler_service.resume(
            company_id=SYSTEM_SCHEDULER_COMPANY_ID,
            schedule_task_id=paused_tasks[0].schedule_task_id,
        )
        logger.info(
            "scheduler.schedule.resumed.schedule_task_id.schedule_id",
            log_label=log_label,
            schedule_task_id=resumed.schedule_task_id,
            schedule_id=resumed.schedule_id,
        )
        return
    request = PlatformScheduleCreateRequest(
        target_service="crm",
        task_name=task_name,
        queue_name=get_task_spec(task_name).queue,
        schedule_type=PlatformScheduleType.CRON,
        cron=cron,
        timezone="UTC",
        payload={},
    )
    created = await scheduler_service.create(
        company_id=SYSTEM_SCHEDULER_COMPANY_ID,
        user_id=None,
        request=request,
    )
    logger.info(
        "scheduler.schedule.created.schedule_task_id.schedule_id",
        log_label=log_label,
        schedule_task_id=created.schedule_task_id,
        schedule_id=created.schedule_id,
    )


async def ensure_platform_schedules(
    scheduler_service: SchedulerService, settings: SchedulerSettings
) -> None:
    if not is_testing():
        _ = await ensure_system_company_exists(
        )
    config = settings.calendar_sync
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=config.enabled,
        task_name=TASK_CALENDAR_SYNC_TICK.name,
        cron=config.cron,
        log_label="Calendar sync",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=config.sync_meeting_reminder_enabled,
        task_name=TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK.name,
        cron=config.sync_meeting_reminder_cron,
        log_label="Calendar Sync meeting reminder",
    )
    mail_sync_cfg = settings.mail_sync
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=mail_sync_cfg.enabled,
        task_name=MAIL_SYNC_TICK.name,
        cron=mail_sync_cfg.cron,
        log_label="Mail sync",
        run_now_on_start=True,
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=mail_sync_cfg.enabled and mail_sync_cfg.idle_enabled,
        task_name=MAIL_IDLE_SUPERVISOR.name,
        cron=mail_sync_cfg.cron,
        log_label="Mail IDLE supervisor",
        run_now_on_start=False,
    )
    billing_cfg = settings.billing.span_settlement
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=billing_cfg.enabled,
        task_name=TASK_SPAN_BILLING_SETTLEMENT_TICK.name,
        cron=billing_cfg.cron,
        log_label="Span billing settlement",
    )
    payment_cfg = settings.payment_providers
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=payment_cfg.sync_enabled,
        task_name=TASK_PAYMENT_SYNC_TICK.name,
        cron=payment_cfg.sync_cron,
        log_label="Payment sync",
    )
    await _ensure_idle_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=TASK_SYNC_LLM_MODELS.name,
        interval_seconds=3600,
        payload={"system_task": LLM_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="LLM models sync",
        run_now_on_start=True,
    )
    await _ensure_idle_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=(not is_testing()) and settings.llm.platform_free_pool.enabled,
        task_name=TASK_REFRESH_PLATFORM_FREE_MODELS.name,
        interval_seconds=settings.llm.platform_free_pool.refresh_interval_seconds,
        payload={"system_task": PLATFORM_FREE_MODELS_SYNC_PAYLOAD_MARKER},
        log_label="Platform free-pool sync",
        run_now_on_start=True,
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=settings.files.retention.purge_enabled,
        task_name=TASK_FILE_RETENTION_PURGE_TICK.name,
        cron=settings.files.retention.purge_cron,
        log_label="File retention purge",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=TASK_FILE_RETENTION_BACKFILL_TICK.name,
        cron=settings.files.retention.purge_cron,
        log_label="File retention backfill",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=TASK_PLATFORM_SCHEDULES_GC_TICK.name,
        cron="0 4 * * *",
        log_label="Platform schedules Redis GC",
    )
    # Тики склада: сверка леджера, GC захватов, min/max, плановый пересчёт.
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_RECONCILE_TICK.name,
        interval_seconds=3600,
        log_label="Stock reconcile",
    )
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_CLAIMS_GC_TICK.name,
        interval_seconds=900,
        log_label="Stock claims GC",
    )
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_REORDER_TICK.name,
        interval_seconds=3600,
        log_label="Stock reorder",
    )
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_CYCLE_COUNT_TICK.name,
        interval_seconds=21600,
        log_label="Stock cycle count",
    )
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_LANE_RELAY_TICK.name,
        interval_seconds=60,
        log_label="Stock lane relay",
    )
    await _ensure_stock_interval_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=STOCK_LANE_GC_TICK.name,
        interval_seconds=86400,
        log_label="Stock lane commit GC",
    )
    if not is_testing():
        await _ensure_idle_interval_schedule(
            scheduler_service=scheduler_service,
            config_enabled=True,
            task_name=TASK_REDIS_INVENTORY_TICK.name,
            interval_seconds=settings.database.redis_inventory_interval_seconds,
            payload={},
            log_label="Redis inventory metrics",
            run_now_on_start=True,
        )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=settings.mcp_catalog.enabled and not is_testing(),
        task_name=TASK_MCP_CATALOG_CRAWL.name,
        cron=settings.mcp_catalog.crawl_cron,
        log_label="MCP catalog crawl",
        run_now_on_start=settings.mcp_catalog.crawl_run_on_start,
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=settings.mcp_catalog.enabled
        and settings.mcp_catalog.auto_provision != "disabled"
        and not is_testing(),
        task_name=TASK_MCP_CATALOG_RESYNC_TOOLS.name,
        cron=settings.mcp_catalog.resync_tools_cron,
        log_label="MCP catalog resync tools",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK.name,
        cron=TOOL_TAG_GROUPS_DESCRIBE_CRON,
        log_label="Tool tag groups describe",
    )
    cfg = settings.rag.ttl
    await _ensure_rag_ttl_cleanup_schedule(
        scheduler_service=scheduler_service,
        config_enabled=cfg.cleanup_enabled,
        task_name=RAG_CLEANUP_EXPIRED_DOCUMENTS_TICK.name,
        cron=cfg.cleanup_cron,
        log_label="RAG TTL cleanup",
    )
    await _ensure_rag_ttl_cleanup_schedule(
        scheduler_service=scheduler_service,
        config_enabled=cfg.reembed_enabled,
        task_name=RAG_REEMBED_STALE_DOCUMENTS_TICK.name,
        cron=cfg.reembed_cron,
        log_label="RAG reembed stale",
    )
    await _ensure_rag_ttl_cleanup_schedule(
        scheduler_service=scheduler_service,
        config_enabled=cfg.orphan_cleanup_enabled,
        task_name=RAG_CLEANUP_ORPHAN_COMPANY_CHUNKS_TICK.name,
        cron=cfg.orphan_cleanup_cron,
        log_label="RAG orphan company chunks cleanup",
    )
    await _ensure_crm_cron_schedule(
        scheduler_service=scheduler_service,
        config_enabled=cfg.reembed_enabled,
        task_name=CRM_REEMBED_STALE_DOCUMENTS.name,
        cron=cfg.reembed_cron,
        log_label="CRM reembed stale",
    )
    await _ensure_crm_cron_schedule(
        scheduler_service=scheduler_service,
        config_enabled=True,
        task_name=CRM_RECONCILE_DAILY_SUMMARY.name,
        cron=CRM_RECONCILE_DAILY_SUMMARY_CRON,
        log_label="CRM daily summary reconcile",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=GEO_OSM_SYNC_TICK.name,
        cron="25 3 * * *",
        log_label="Geo OSM sync",
    )
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=GEO_TILES_SYNC.name,
        cron="40 4 * * 0",
        log_label="Geo tiles sync",
    )
    # Telegram getUpdates-поллинг customer-auth: минутный тик, сам таска
    # держит long-poll до 55 с; при живом поллере тик сразу выходит по lock.
    await _ensure_calendar_schedule(
        scheduler_service=scheduler_service,
        config_enabled=not is_testing(),
        task_name=CUSTOMER_AUTH_TG_POLL.name,
        cron="* * * * *",
        log_label="Customer auth Telegram poll",
    )
    if not is_testing():
        await ensure_search_crawl_schedules(scheduler_service=scheduler_service)


app = create_service_app(
    "scheduler",
    SchedulerSettings,
    SchedulerDi,
    database="shared_url",
    operations=SCHEDULER_OPERATIONS,
    lifecycle=(recipe(ensure_platform_schedules),),
    routers=[api_v1_router],
    cors_origins=["*"],
    title="Platform Scheduler",
    description="Единый cron/control-plane для всех сервисов",
    api_version="v1",
    documentation_gateway_prefix="scheduler",
)


if __name__ == "__main__":
    from core.app.server import serve

    serve("scheduler", "apps.scheduler.main:app", get_scheduler_settings())
