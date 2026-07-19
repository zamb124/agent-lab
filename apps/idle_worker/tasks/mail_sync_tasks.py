"""
Фоновые задачи автосинхронизации почты (IMAP UID-курсоры + notify).
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from apps.flows.config import get_settings
from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import IdleWorkerContainer, get_container
from core.logging import get_logger
from core.mail.models import InboundMailMessage, MailboxBinding, MailSyncErrorKind
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


async def _send_new_mail_notifications(
    *,
    container: IdleWorkerContainer,
    binding: MailboxBinding,
    messages: list[InboundMailMessage],
    dedup_ttl_seconds: int,
) -> int:
    if binding.user_id is None:
        raise ValueError(
            f"mail sync notify requires user_id for mailbox_binding_id={binding.mailbox_binding_id}"
        )
    sent = 0
    for message in messages:
        dedup_key = (
            f"mail:notify:{binding.company_id}:{binding.user_id}:"
            f"{binding.mailbox_binding_id}:{message.uid}"
        )
        existing = await container.shared_storage.get(key=dedup_key, force_global=True)
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
            user_id=binding.user_id,
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
        _ = await container.shared_storage.set(
            key=dedup_key,
            value=json.dumps({"sent_at": datetime.now(timezone.utc).isoformat()}),
            ttl=dedup_ttl_seconds,
            force_global=True,
        )
        sent += 1
    return sent


async def _sync_single_binding(
    *,
    container: IdleWorkerContainer,
    semaphore: asyncio.Semaphore,
    binding: MailboxBinding,
    max_new_messages: int,
    dedup_ttl_seconds: int,
) -> tuple[int, int, bool, str | None]:
    async with semaphore:
        result = await container.mail_service.sync_user_inbox(
            binding,
            max_new_messages=max_new_messages,
        )
        if result.skipped_reason is not None:
            return 0, 0, False, result.skipped_reason
        if result.bootstrap:
            return 0, 0, True, None
        if len(result.new_messages) == 0:
            return 0, 0, False, None
        sent = await _send_new_mail_notifications(
            container=container,
            binding=binding,
            messages=result.new_messages,
            dedup_ttl_seconds=dedup_ttl_seconds,
        )
        return len(result.new_messages), sent, False, None


@idle_broker.task(task_name="mail_sync_tick", queue_name="idle")
async def mail_sync_tick(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
) -> dict[str, int]:
    settings = get_settings()
    config = settings.mail_sync
    if not config.enabled:
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
        }

    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required for mail sync task")

    container = get_container()
    candidates = await container.mail_service.list_sync_candidates(
        limit=config.max_bindings_per_tick,
        auth_error_cooldown_seconds=config.auth_error_cooldown_seconds,
    )
    if len(candidates) > config.batch_size:
        candidates = candidates[: config.batch_size]

    stats = _TickStats(bindings_total=len(candidates))
    if stats.bindings_total == 0:
        logger.info("mail_sync_tick: no enabled bindings")
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
        }

    semaphore = asyncio.Semaphore(config.max_parallel_bindings)
    tasks = [
        _sync_single_binding(
            container=container,
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
            await container.mail_service.record_sync_failure(
                binding,
                error_kind=failure_kind,
                error_message=str(outcome),
            )
            logger.error(
                "mail_sync_tick: sync failed for mailbox_binding_id=%s company_id=%s user_id=%s error_type=%s failure_kind=%s error=%s",
                binding.mailbox_binding_id,
                binding.company_id,
                binding.user_id,
                type(outcome).__name__,
                failure_kind.value,
                str(outcome),
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

    logger.info(
        "mail_sync_tick done: bindings_total=%s success=%s failed=%s skipped=%s auth_failed=%s network_failed=%s validation_failed=%s unknown_failed=%s new_messages=%s notifications=%s bootstraps=%s schedule_task_id=%s company_id=%s",
        stats.bindings_total,
        stats.bindings_success,
        stats.bindings_failed,
        stats.bindings_skipped,
        stats.failures_auth,
        stats.failures_network,
        stats.failures_validation,
        stats.failures_unknown,
        stats.messages_new,
        stats.notifications_sent,
        stats.bootstraps,
        schedule_task_id,
        company_id,
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
    }
