"""
Фоновые задачи автосинхронизации почты (IMAP UID-курсоры + notify).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from apps.flows.src.tasks.task_names import TASK_DISPATCH_EMAIL_TRIGGERS
from apps.idle_worker.di import Di
from apps.idle_worker.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from apps.idle_worker.tasks.mail_recipients import mailbox_recipient_user_ids
from core.config import get_settings
from core.events import publish_event_to_users
from core.logging import get_logger
from core.mail.enqueue import enqueue_mail_sync_tick_continuation
from core.mail.events import MAIL_MESSAGE_UPSERTED
from core.mail.models import (
    InboundMailMessage,
    MailboxBinding,
    MailSyncErrorKind,
)
from core.mail.service import to_message_list_item
from core.mail.task_names import MAIL_SYNC_BINDING, MAIL_SYNC_TICK
from core.mail.threads import thread_id_for_message
from core.tasks import enqueue, platform_task
from core.types import JsonObject
from core.websocket.publisher import (
    Notification,
    NotificationAction,
    NotificationType,
    notify_user,
)

logger = get_logger(__name__)


@dataclass(slots=True)
class _TickStats:
    bindings_total: int = 0
    bindings_success: int = 0
    bindings_failed: int = 0
    bindings_skipped: int = 0
    failures_auth: int = 0
    failures_network: int = 0
    failures_validation: int = 0
    failures_unknown: int = 0
    messages_new: int = 0
    notifications_sent: int = 0
    bootstraps: int = 0
    bindings_pending: int = 0
    max_lag_seconds: int = 0


def _classify_failure(error: BaseException) -> MailSyncErrorKind:
    message = str(error).lower()
    if isinstance(error, httpx.HTTPStatusError):
        if error.response.status_code in {401, 403}:
            return MailSyncErrorKind.AUTH
        return MailSyncErrorKind.NETWORK
    if isinstance(error, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return MailSyncErrorKind.NETWORK
    if isinstance(error, ValueError):
        return MailSyncErrorKind.VALIDATION
    if "login failed" in message or "authentication" in message or "auth" in message:
        return MailSyncErrorKind.AUTH
    if "timeout" in message or "connect" in message or "network" in message:
        return MailSyncErrorKind.NETWORK
    return MailSyncErrorKind.UNKNOWN


async def _recipient_user_ids(
    di: Di, binding: MailboxBinding
) -> list[str]:
    return await mailbox_recipient_user_ids(di.authz_service, binding)


async def _publish_message_upserted(
    *,
    di: Di,
    binding: MailboxBinding,
    messages: list[InboundMailMessage],
    folder: str = "INBOX",
) -> None:
    recipients = await _recipient_user_ids(di, binding)
    if not recipients:
        return
    for message in messages:
        list_item = to_message_list_item(message)
        unread_delta = 1 if message.unread else 0
        payload: JsonObject = {
            "mailbox_binding_id": binding.mailbox_binding_id,
            "folder": folder,
            "uid": message.uid,
            "thread_id": thread_id_for_message(message),
            "list_item": list_item.model_dump(mode="json"),
            "unread_delta": unread_delta,
            "flagged": message.flagged,
        }
        if message.message_id is not None:
            payload["message_id"] = message.message_id
        await publish_event_to_users(
            recipients,
            MAIL_MESSAGE_UPSERTED,
            payload,
            company_id=binding.company_id,
        )


async def _send_new_mail_notifications(
    *,
    di: Di,
    binding: MailboxBinding,
    messages: list[InboundMailMessage],
    dedup_ttl_seconds: int,
) -> int:
    recipients = await _recipient_user_ids(di, binding)
    if not recipients:
        return 0
    sent = 0
    for message in messages:
        for user_id in recipients:
            dedup_key = (
                f"mail:notify:{binding.company_id}:{user_id}:"
                f"{binding.mailbox_binding_id}:{message.uid}"
            )
            existing = await di.shared_storage.get(key=dedup_key)
            if existing is not None:
                continue
            from_display = message.from_address if message.from_address is not None else "—"
            subject_display = message.subject if message.subject is not None else "(no subject)"
            notify_data: JsonObject = {
                "company_id": binding.company_id,
                "mailbox_binding_id": binding.mailbox_binding_id,
                "uid": message.uid,
                "email_address": binding.email_address,
                "folder_role": "inbox",
            }
            if message.message_id is not None:
                notify_data["message_id"] = message.message_id
            await notify_user(
                user_id=user_id,
                notification=Notification(
                    type=NotificationType.MAIL_NEW_MESSAGE,
                    title="Новое письмо",
                    message=f"{from_display}: {subject_display}",
                    title_i18n_key="mail:notifications.new_message_title",
                    message_i18n_key="mail:notifications.new_message_message",
                    title_i18n_vars={},
                    message_i18n_vars={
                        "from": from_display,
                        "subject": subject_display,
                        "email_address": binding.email_address,
                    },
                    service="mail",
                    data=notify_data,
                    action_url="#mail",
                    action_label="Открыть письмо",
                    action_label_i18n_key="mail:notifications.open_message",
                    actions=[
                        NotificationAction(
                            label="Открыть письмо",
                            url="#mail",
                            label_i18n_key="mail:notifications.open_message",
                            data={
                                "mailbox_binding_id": binding.mailbox_binding_id,
                                "uid": message.uid,
                                "folder_role": "inbox",
                            },
                        )
                    ],
                ),
            )
            _ = await di.shared_storage.set(
                key=dedup_key,
                value=json.dumps({"sent_at": datetime.now(timezone.utc).isoformat()}),
                ttl=dedup_ttl_seconds,
            )
            sent += 1
    await _publish_message_upserted(
        di=di, binding=binding, messages=messages
    )
    return sent


async def _sync_single_binding(
    *,
    di: Di,
    semaphore: asyncio.Semaphore,
    binding: MailboxBinding,
    max_new_messages: int,
    dedup_ttl_seconds: int,
) -> tuple[int, int, bool, str | None]:
    async with semaphore:
        previous = await enter_mail_binding_context(di.authz_service, binding)
        try:
            result = await di.mail_service.sync_binding(
                binding,
                max_new_messages=max_new_messages,
                backfill_batch_size=get_settings().mail_sync.backfill_batch_size,
            )
        finally:
            leave_mail_binding_context(previous)
        if result.skipped_reason is not None:
            return 0, 0, False, result.skipped_reason
        if result.bootstrap:
            return 0, 0, True, None
        if len(result.new_messages) == 0:
            return 0, 0, False, None
        sent = await _send_new_mail_notifications(
            di=di,
            binding=binding,
            messages=result.new_messages,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        await _enqueue_email_triggers(
            binding=binding,
            messages=result.new_messages,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        return len(result.new_messages), sent, False, None


async def _enqueue_email_triggers(
    *,
    binding: MailboxBinding,
    messages: list[InboundMailMessage],
    dedup_ttl_seconds: int,
) -> None:
    """Email-триггеры исполняет flows_worker: письма уходят без байтов вложений."""
    _ = await enqueue(
        TASK_DISPATCH_EMAIL_TRIGGERS,
        company_id=binding.company_id,
        mailbox_binding_id=binding.mailbox_binding_id,
        messages=[
            message.model_copy(update={"attachments": []}).model_dump(mode="json")
            for message in messages
        ],
        dedup_ttl_seconds=dedup_ttl_seconds,
    )


def _empty_tick_result() -> dict[str, int]:
    return {
        "bindings_total": 0,
        "bindings_success": 0,
        "bindings_failed": 0,
        "bindings_skipped": 0,
        "auth_failed": 0,
        "network_failed": 0,
        "validation_failed": 0,
        "unknown_failed": 0,
        "messages_new": 0,
        "notifications_sent": 0,
        "bootstraps": 0,
        "bindings_pending": 0,
        "max_lag_seconds": 0,
    }


@platform_task(MAIL_SYNC_TICK)
async def mail_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    drain_depth: int = 0,
    *,
    di: Di,
) -> dict[str, int]:
    settings = get_settings()
    config = settings.mail_sync
    if not config.enabled:
        return _empty_tick_result()

    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for mail sync task")

    lag = await di.mail_service.sync_lag_stats(
        auth_error_cooldown_seconds=config.auth_error_cooldown_seconds,
    )
    candidates = await di.mail_service.list_sync_candidates(
        limit=config.max_bindings_per_tick,
        auth_error_cooldown_seconds=config.auth_error_cooldown_seconds,
    )
    pending_after_batch = max(0, len(candidates) - config.batch_size)
    if len(candidates) > config.batch_size:
        candidates = candidates[: config.batch_size]

    stats = _TickStats(
        bindings_total=len(candidates),
        bindings_pending=pending_after_batch,
        max_lag_seconds=lag.max_lag_seconds,
    )
    if stats.bindings_total == 0:
        logger.info("idle.mail_sync_tick", pending=lag.bindings_pending, max_lag_seconds=lag.max_lag_seconds)
        return {
            **_empty_tick_result(),
            "bindings_pending": lag.bindings_pending,
            "max_lag_seconds": lag.max_lag_seconds,
        }

    semaphore = asyncio.Semaphore(config.max_parallel_bindings)
    tasks = [
        _sync_single_binding(
            di=di,
            semaphore=semaphore,
            binding=binding,
            max_new_messages=config.max_new_messages_per_binding,
            dedup_ttl_seconds=config.notification_dedup_ttl_seconds,
        )
        for binding in candidates
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for index, outcome in enumerate(results):
        binding = candidates[index]
        if isinstance(outcome, BaseException):
            stats.bindings_failed += 1
            failure_kind = _classify_failure(outcome)
            if failure_kind == MailSyncErrorKind.AUTH:
                stats.failures_auth += 1
            elif failure_kind == MailSyncErrorKind.NETWORK:
                stats.failures_network += 1
            elif failure_kind == MailSyncErrorKind.VALIDATION:
                stats.failures_validation += 1
            else:
                stats.failures_unknown += 1
            await di.mail_service.record_sync_failure(
                binding,
                error_kind=failure_kind,
                error_message=str(outcome),
            )
            logger.error(
                "idle.mail_sync_tick",
                mailbox_binding_id=binding.mailbox_binding_id,
                company_id=binding.company_id,
                user_id=binding.user_id,
                error_type=type(outcome).__name__,
                failure_kind=failure_kind.value,
                error=str(outcome),
                exc_info=(type(outcome), outcome, outcome.__traceback__),
            )
            continue
        new_count, sent_count, bootstrap, skipped_reason = outcome
        if skipped_reason is not None:
            stats.bindings_skipped += 1
            stats.bindings_success += 1
            continue
        stats.bindings_success += 1
        if bootstrap:
            stats.bootstraps += 1
        stats.messages_new += new_count
        stats.notifications_sent += sent_count

    if (
        pending_after_batch > 0
        and drain_depth < config.max_drain_continuations
    ):
        await enqueue_mail_sync_tick_continuation(
            schedule_task_id=schedule_task_id,
            company_id=company_id,
            drain_depth=drain_depth + 1,
        )

    logger.info(
        "idle.mail_sync_tick",
        bindings_total=stats.bindings_total,
        success=stats.bindings_success,
        failed=stats.bindings_failed,
        skipped=stats.bindings_skipped,
        auth_failed=stats.failures_auth,
        network_failed=stats.failures_network,
        validation_failed=stats.failures_validation,
        unknown_failed=stats.failures_unknown,
        new_messages=stats.messages_new,
        notifications=stats.notifications_sent,
        bootstraps=stats.bootstraps,
        bindings_pending=stats.bindings_pending,
        max_lag_seconds=stats.max_lag_seconds,
        drain_depth=drain_depth,
        schedule_task_id=schedule_task_id,
        company_id=company_id,
    )
    return {
        "bindings_total": stats.bindings_total,
        "bindings_success": stats.bindings_success,
        "bindings_failed": stats.bindings_failed,
        "bindings_skipped": stats.bindings_skipped,
        "auth_failed": stats.failures_auth,
        "network_failed": stats.failures_network,
        "validation_failed": stats.failures_validation,
        "unknown_failed": stats.failures_unknown,
        "messages_new": stats.messages_new,
        "notifications_sent": stats.notifications_sent,
        "bootstraps": stats.bootstraps,
        "bindings_pending": stats.bindings_pending,
        "max_lag_seconds": stats.max_lag_seconds,
    }


@platform_task(MAIL_SYNC_BINDING)
async def mail_sync_binding_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    di: Di,
) -> dict[str, int | bool | str | None]:
    settings = get_settings()
    config = settings.mail_sync
    binding = await MailboxBinding.by_mailbox_binding_id(
        company_id, mailbox_binding_id
    )
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    previous = await enter_mail_binding_context(di.authz_service, binding)
    try:
        result = await di.mail_service.sync_binding(
            binding,
            max_new_messages=config.max_new_messages_per_binding,
            backfill_batch_size=config.backfill_batch_size,
        )
    finally:
        leave_mail_binding_context(previous)
    if (
        result.skipped_reason is None
        and not result.bootstrap
        and result.new_messages
    ):
        _ = await _send_new_mail_notifications(
            di=di,
            binding=binding,
            messages=result.new_messages,
            dedup_ttl_seconds=config.notification_dedup_ttl_seconds,
        )
        await _enqueue_email_triggers(
            binding=binding,
            messages=result.new_messages,
            dedup_ttl_seconds=config.notification_dedup_ttl_seconds,
        )
    return {
        "mailbox_binding_id": mailbox_binding_id,
        "bootstrap": result.bootstrap,
        "new_messages": len(result.new_messages),
        "backfill_remaining": result.backfill_remaining,
        "skipped_reason": result.skipped_reason,
    }
