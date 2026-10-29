"""
Фоновые задачи автосинхронизации календаря.
"""

from __future__ import annotations

import asyncio
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx2

from apps.idle.di import Di
from apps.idle.tasks.task_names import (
    TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK,
    TASK_CALENDAR_SYNC_TICK,
)
from core.calendar.events import CALENDAR_EVENT_CREATED
from core.calendar.service import (
    SYNC_LINK_TOKEN_META,
    CalendarReauthRequiredError,
    CalendarService,
    calendar_integration_from_credential,
    calendar_source_for_provider,
)
from core.config import get_settings
from core.events import publish_event_to_user
from core.integrations.models import IntegrationCredential, IntegrationProvider
from core.logging import get_logger
from core.models import CalendarEvent, CalendarEventSource, CalendarIntegration, CalendarProvider
from core.tasks import platform_task
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
    if isinstance(error, httpx2.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return "auth"
        return "network"
    if isinstance(error, (httpx2.TimeoutException, httpx2.ConnectError, httpx2.NetworkError)):
        return "network"
    if isinstance(error, ValueError):
        return "validation"
    return "unknown"


async def _load_existing_event_ids(
    *,
    calendar_service: CalendarService,
    company_id: str,
    user_id: str,
    source: CalendarEventSource,
    start_at: datetime,
    end_at: datetime,
) -> set[str]:
    events = await calendar_service.list_events_by_start_at_asc(
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
    di: Di,
    company_id: str,
    user_id: str,
    provider: CalendarProvider,
    new_event_ids: set[str],
    dedup_ttl_seconds: int,
) -> int:
    sent = 0
    for event_id in new_event_ids:
        dedup_key = f"calendar:notify:{company_id}:{user_id}:{provider.value}:{event_id}"
        existing = await di.shared_storage.get(key=dedup_key)
        if existing is not None:
            continue
        await publish_event_to_user(
            user_id,
            CALENDAR_EVENT_CREATED,
            {
                "event_id": event_id,
                "provider": provider.value,
                "company_id": company_id,
                "start_at": "",
            },
            company_id=company_id,
        )
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
        _ = await di.shared_storage.set(
            key=dedup_key,
            value=json.dumps({"sent_at": datetime.now(timezone.utc).isoformat()}),
            ttl=dedup_ttl_seconds,
        )
        sent += 1
    return sent


async def _sync_single_integration(
    *,
    di: Di,
    semaphore: asyncio.Semaphore,
    integration: CalendarIntegration,
    start_at: datetime,
    end_at: datetime,
    dedup_ttl_seconds: int,
) -> tuple[int, int]:
    async with semaphore:
        calendar_service = di.calendar_service
        provider = CalendarProvider(integration.provider)
        source = calendar_source_for_provider(provider)

        before_ids = await _load_existing_event_ids(
            calendar_service=calendar_service,
            company_id=integration.company_id,
            user_id=integration.user_id,
            source=source,
            start_at=start_at,
            end_at=end_at,
        )
        _ = await calendar_service.run_sync(
            user_id=integration.user_id,
            company_id=integration.company_id,
            start_at=start_at,
            end_at=end_at,
            integration_id=integration.integration_id,
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
            di=di,
            company_id=integration.company_id,
            user_id=integration.user_id,
            provider=provider,
            new_event_ids=new_event_ids,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        return len(new_event_ids), sent


@platform_task(TASK_CALENDAR_SYNC_TICK)
async def calendar_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
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


    start_tick = datetime.now(timezone.utc)
    start_at = start_tick - timedelta(days=config.lookback_days)
    end_at = _add_months(start_tick, config.lookahead_months)

    calendar_providers = (
        IntegrationProvider.GOOGLE,
        IntegrationProvider.YANDEX,
        IntegrationProvider.MAILRU,
        IntegrationProvider.CALDAV,
    )
    all_creds: list[IntegrationCredential] = []
    for calendar_provider in calendar_providers:
        all_creds.extend(
            await IntegrationCredential.list_by_provider_service_updated_at_asc(
                provider=calendar_provider,
                service="calendar",
                limit=config.max_integrations_per_tick,
            )
        )
    integrations = [
        integration
        for c in all_creds
        if (integration := calendar_integration_from_credential(c)).settings.sync_enabled
    ]
    if len(integrations) > config.batch_size:
        integrations = integrations[: config.batch_size]

    stats = _TickStats(integrations_total=len(integrations))
    if stats.integrations_total == 0:
        logger.info("idle.calendar_sync_tick")
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
            di=di,
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
                "idle.calendar_sync_tick",
                integration_id=integration.integration_id,
                provider=CalendarProvider(integration.provider).value,
                company_id=integration.company_id,
                user_id=integration.user_id,
                error_type=type(outcome).__name__,
                failure_kind=failure_kind,
                error=str(outcome),
                exc_info=(type(outcome), outcome, outcome.__traceback__),
            )
            continue
        new_events_count, sent_notifications = outcome
        stats.integrations_success += 1
        stats.events_new += new_events_count
        stats.notifications_sent += sent_notifications

    logger.info(
        "idle.calendar_sync_tick",
        integrations_total=stats.integrations_total,
        success=stats.integrations_success,
        failed=stats.integrations_failed,
        auth_failed=stats.failures_auth,
        network_failed=stats.failures_network,
        validation_failed=stats.failures_validation,
        unknown_failed=stats.failures_unknown,
        new_events=stats.events_new,
        notifications=stats.notifications_sent,
        schedule_task_id=schedule_task_id,
        company_id=company_id,
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


@platform_task(TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK)
async def calendar_sync_meeting_reminder_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
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

    events = await CalendarEvent.list_unsent_platform_meeting_reminders_by_start_at_asc(
        window_start=window_start,
        window_end=window_end,
        limit=config.sync_meeting_reminder_limit,
    )
    calendar_service = di.calendar_service
    sent = 0
    for event in events:
        action_url = event.deep_link
        if action_url is None or action_url == "":
            if SYNC_LINK_TOKEN_META not in event.metadata:
                raise ValueError(f"Event {event.event_id} has no {SYNC_LINK_TOKEN_META} in metadata.")
            token = event.metadata[SYNC_LINK_TOKEN_META]
            if token == "":
                raise ValueError(f"Event {event.event_id} has no {SYNC_LINK_TOKEN_META} in metadata.")
            action_url = await di.short_link_service.mint_sync_call_join(
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
        "idle.calendar_sync_meeting_reminder_tick",
        events=len(events),
        notifications=sent,
        schedule_task_id=schedule_task_id,
        company_id=company_id,
    )
    return {"events_checked": len(events), "notifications_sent": sent}
