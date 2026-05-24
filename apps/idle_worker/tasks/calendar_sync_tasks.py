"""
Фоновые задачи автосинхронизации календаря.
"""

from __future__ import annotations

import asyncio
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from apps.flows.config import get_settings
from apps.flows.src.container import get_container
from apps.idle_worker.broker import broker as idle_broker
from core.calendar.service import CalendarReauthRequiredError, _credential_to_calendar_integration
from core.integrations.models import IntegrationProvider
from core.logging import get_logger
from core.models import CalendarEventSource, CalendarProvider
from core.websocket.publisher import Notification, NotificationType, notify_user

logger = get_logger(__name__)


def _add_months(anchor: datetime, months: int) -> datetime:
    if months < 0:
        raise ValueError("months must be non-negative")
    year = anchor.year + (anchor.month - 1 + months) // 12
    month = (anchor.month - 1 + months) % 12 + 1
    day = min(anchor.day, monthrange(year, month)[1])
    return anchor.replace(year=year, month=month, day=day)


@dataclass(slots=True)
class _TickStats:
    integrations_total: int = 0
    integrations_success: int = 0
    integrations_failed: int = 0
    failures_auth: int = 0
    failures_network: int = 0
    failures_validation: int = 0
    failures_unknown: int = 0
    events_new: int = 0
    notifications_sent: int = 0


def _classify_failure(error: BaseException) -> str:
    if isinstance(error, CalendarReauthRequiredError):
        return "auth"
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return "auth"
        return "network"
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return "network"
    if isinstance(error, ValueError):
        return "validation"
    return "unknown"


async def _load_existing_event_ids(
    *,
    calendar_service,
    company_id: str,
    user_id: str,
    source: CalendarEventSource,
    start_at: datetime,
    end_at: datetime,
) -> set[str]:
    events = await calendar_service.list_events(
        company_id=company_id,
        user_id=user_id,
        start_at=start_at,
        end_at=end_at,
        include_sources={source},
        limit=5000,
    )
    return {event.event_id for event in events}


async def _send_new_event_notifications(
    *,
    container,
    company_id: str,
    user_id: str,
    provider: CalendarProvider,
    new_event_ids: set[str],
    dedup_ttl_seconds: int,
) -> int:
    sent = 0
    for event_id in new_event_ids:
        dedup_key = f"calendar:notify:{company_id}:{user_id}:{provider.value}:{event_id}"
        existing = await container.shared_storage.get(key=dedup_key, force_global=True)
        if existing is not None:
            continue
        await notify_user(
            user_id=user_id,
            notification=Notification(
                type=NotificationType.CALENDAR_NEW_EVENT,
                title="Новое событие в календаре",
                message=f"Появилось новое событие из {provider.value}",
                service="calendar",
                data={
                    "event_id": event_id,
                    "provider": provider.value,
                    "company_id": company_id,
                },
                action_url="/",
            ),
        )
        await container.shared_storage.set(
            key=dedup_key,
            value=json.dumps({"sent_at": datetime.now(timezone.utc).isoformat()}),
            ttl=dedup_ttl_seconds,
            force_global=True,
        )
        sent += 1
    return sent


async def _sync_single_integration(
    *,
    container,
    semaphore: asyncio.Semaphore,
    integration,
    start_at: datetime,
    end_at: datetime,
    dedup_ttl_seconds: int,
) -> tuple[int, int]:
    async with semaphore:
        calendar_service = container.calendar_service
        provider = CalendarProvider(integration.provider)
        if provider == CalendarProvider.GOOGLE:
            source = CalendarEventSource.GOOGLE
        elif provider == CalendarProvider.YANDEX:
            source = CalendarEventSource.YANDEX
        else:
            raise ValueError(f"Unsupported calendar provider for background sync: {provider}")

        before_ids = await _load_existing_event_ids(
            calendar_service=calendar_service,
            company_id=integration.company_id,
            user_id=integration.user_id,
            source=source,
            start_at=start_at,
            end_at=end_at,
        )
        await calendar_service.run_sync(
            user_id=integration.user_id,
            company_id=integration.company_id,
            start_at=start_at,
            end_at=end_at,
            provider=provider,
        )
        after_ids = await _load_existing_event_ids(
            calendar_service=calendar_service,
            company_id=integration.company_id,
            user_id=integration.user_id,
            source=source,
            start_at=start_at,
            end_at=end_at,
        )
        new_event_ids = after_ids - before_ids
        if not integration.settings.notifications_enabled or len(new_event_ids) == 0:
            return len(new_event_ids), 0
        sent = await _send_new_event_notifications(
            container=container,
            company_id=integration.company_id,
            user_id=integration.user_id,
            provider=provider,
            new_event_ids=new_event_ids,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        return len(new_event_ids), sent


@idle_broker.task(task_name="calendar_sync_tick", queue_name="idle")
async def calendar_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    settings = get_settings()
    config = settings.calendar_sync
    if not config.enabled:
        return {
            "integrations_total": 0,
            "integrations_success": 0,
            "integrations_failed": 0,
            "auth_failed": 0,
            "network_failed": 0,
            "validation_failed": 0,
            "unknown_failed": 0,
            "events_new": 0,
            "notifications_sent": 0,
        }

    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for calendar sync task")

    container = get_container()

    start_tick = datetime.now(timezone.utc)
    start_at = start_tick - timedelta(days=config.lookback_days)
    end_at = _add_months(start_tick, config.lookahead_months)

    credential_repository = container.integration_credential_repository
    google_creds = await credential_repository.list_by_provider_service(
        provider=IntegrationProvider.GOOGLE,
        service="calendar",
        limit=config.max_integrations_per_tick,
    )
    yandex_creds = await credential_repository.list_by_provider_service(
        provider=IntegrationProvider.YANDEX,
        service="calendar",
        limit=config.max_integrations_per_tick,
    )
    all_creds = google_creds + yandex_creds
    integrations = [
        integration
        for c in all_creds
        if (integration := _credential_to_calendar_integration(c)).settings.sync_enabled
    ]
    if len(integrations) > config.batch_size:
        integrations = integrations[: config.batch_size]

    stats = _TickStats(integrations_total=len(integrations))
    if stats.integrations_total == 0:
        logger.info("calendar_sync_tick: no enabled integrations")
        return {
            "integrations_total": 0,
            "integrations_success": 0,
            "integrations_failed": 0,
            "auth_failed": 0,
            "network_failed": 0,
            "validation_failed": 0,
            "unknown_failed": 0,
            "events_new": 0,
            "notifications_sent": 0,
        }

    semaphore = asyncio.Semaphore(config.max_parallel_integrations)
    tasks = [
        _sync_single_integration(
            container=container,
            semaphore=semaphore,
            integration=integration,
            start_at=start_at,
            end_at=end_at,
            dedup_ttl_seconds=config.notification_dedup_ttl_seconds,
        )
        for integration in integrations
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for index, outcome in enumerate(results):
        integration = integrations[index]
        if isinstance(outcome, BaseException):
            stats.integrations_failed += 1
            failure_kind = _classify_failure(outcome)
            if failure_kind == "auth":
                stats.failures_auth += 1
            elif failure_kind == "network":
                stats.failures_network += 1
            elif failure_kind == "validation":
                stats.failures_validation += 1
            else:
                stats.failures_unknown += 1
            logger.error(
                "calendar_sync_tick: sync failed for integration_id=%s provider=%s company_id=%s user_id=%s error_type=%s failure_kind=%s error=%s",
                integration.integration_id,
                CalendarProvider(integration.provider).value,
                integration.company_id,
                integration.user_id,
                type(outcome).__name__,
                failure_kind,
                str(outcome),
                exc_info=(type(outcome), outcome, outcome.__traceback__),
            )
            continue
        new_events_count, sent_notifications = outcome
        stats.integrations_success += 1
        stats.events_new += new_events_count
        stats.notifications_sent += sent_notifications

    logger.info(
        "calendar_sync_tick done: integrations_total=%s success=%s failed=%s auth_failed=%s network_failed=%s validation_failed=%s unknown_failed=%s new_events=%s notifications=%s schedule_task_id=%s company_id=%s",
        stats.integrations_total,
        stats.integrations_success,
        stats.integrations_failed,
        stats.failures_auth,
        stats.failures_network,
        stats.failures_validation,
        stats.failures_unknown,
        stats.events_new,
        stats.notifications_sent,
        schedule_task_id,
        company_id,
    )
    return {
        "integrations_total": stats.integrations_total,
        "integrations_success": stats.integrations_success,
        "integrations_failed": stats.integrations_failed,
        "auth_failed": stats.failures_auth,
        "network_failed": stats.failures_network,
        "validation_failed": stats.failures_validation,
        "unknown_failed": stats.failures_unknown,
        "events_new": stats.events_new,
        "notifications_sent": stats.notifications_sent,
    }


@idle_broker.task(task_name="calendar_sync_meeting_reminder_tick", queue_name="idle")
async def calendar_sync_meeting_reminder_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    """
    Напоминание за ~15 минут до start_at: platform-событие с Sync-ссылкой,
    окно start_at в UTC [now+14m, now+16m). Идемпотентность — metadata.sync_join_reminder_sent_at.
    """
    settings = get_settings()
    config = settings.calendar_sync
    if not config.sync_meeting_reminder_enabled:
        return {"events_checked": 0, "notifications_sent": 0}

    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for calendar sync meeting reminder task")

    now = datetime.now(timezone.utc)
    window_start = now + timedelta(minutes=14)
    window_end = now + timedelta(minutes=16)

    container = get_container()
    events = await container.calendar_event_repository.list_platform_sync_meeting_reminder_window(
        window_start=window_start,
        window_end=window_end,
        limit=config.sync_meeting_reminder_limit,
    )
    calendar_service = container.calendar_service
    sent = 0
    for event in events:
        action_url = event.deep_link
        if action_url is None or action_url == "":
            token = event.metadata.get("sync_link_token")
            if not token:
                raise ValueError(f"У события {event.event_id} нет sync_link_token в metadata.")
            action_url = await container.short_link_service.mint_sync_call_join(
                token, event.end_at, event.company_id
            )
        recipients = await calendar_service.sync_meeting_reminder_recipient_user_ids(event)
        for user_id in recipients:
            await notify_user(
                user_id=user_id,
                notification=Notification(
                    type=NotificationType.CALENDAR_SYNC_MEETING_REMINDER,
                    title="Скоро встреча Sync",
                    message=f"Через 15 минут: «{event.title}». Перейдите по ссылке, чтобы подключиться.",
                    service="calendar",
                    priority="normal",
                    data={
                        "event_id": event.event_id,
                        "company_id": event.company_id,
                        "start_at": event.start_at.isoformat(),
                    },
                    action_url=action_url,
                ),
            )
            sent += 1
        await calendar_service.mark_sync_meeting_reminder_sent(event.event_id, event.company_id)

    logger.info(
        "calendar_sync_meeting_reminder_tick done: events=%s notifications=%s schedule_task_id=%s company_id=%s",
        len(events),
        sent,
        schedule_task_id,
        company_id,
    )
    return {"events_checked": len(events), "notifications_sent": sent}
