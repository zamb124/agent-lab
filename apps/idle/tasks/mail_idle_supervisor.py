"""IMAP IDLE supervisor: wake → mail_sync_binding."""

from __future__ import annotations

import asyncio

from apps.idle.di import Di
from core.config import get_settings
from core.logging import get_logger
from core.mail.enqueue import enqueue_mail_sync_binding
from core.mail.models import (
    INBOX_FOLDER,
    CompanyMailConnection,
    MailboxBinding,
    MailboxBindingKind,
    MailIdleWakeKind,
)
from core.mail.service import MailService
from core.mail.task_names import MAIL_IDLE_SUPERVISOR
from core.tasks import platform_task

logger = get_logger(__name__)


async def _idle_one_binding(
    *,
    mail_service: MailService,
    binding: MailboxBinding,
    timeout_seconds: float,
) -> bool:
    connection = await CompanyMailConnection.get(binding.company_mail_connection_id)
    if connection is None:
        return False
    port = mail_service.port_for_connection(connection)
    secret = mail_service.binding_secret(binding)
    try:
        session = await port.open_idle_session(secret, mailbox=INBOX_FOLDER)
    except Exception as exc:
        logger.warning(
            "mail.idle.open_failed",
            mailbox_binding_id=binding.mailbox_binding_id,
            error=str(exc),
        )
        return False
    woke = False
    try:
        wake = await session.wait_wake(timeout_seconds=timeout_seconds)
        if wake.kind in {
            MailIdleWakeKind.EXISTS,
            MailIdleWakeKind.RECENT,
            MailIdleWakeKind.EXPUNGE,
        }:
            woke = True
            await enqueue_mail_sync_binding(
                company_id=binding.company_id,
                mailbox_binding_id=binding.mailbox_binding_id,
            )
    except Exception as exc:
        logger.warning(
            "mail.idle.wait_failed",
            mailbox_binding_id=binding.mailbox_binding_id,
            error=str(exc),
        )
    finally:
        try:
            await session.aclose()
        except Exception as exc:
            logger.warning(
                "mail.idle.close_failed",
                mailbox_binding_id=binding.mailbox_binding_id,
                error=str(exc),
            )
    return woke


@platform_task(MAIL_IDLE_SUPERVISOR)
async def mail_idle_supervisor_task(
    schedule_task_id: str | None = None,
    company_id: str | None = None,
    *,
    di: Di,
) -> dict[str, int]:
    """Параллельный IDLE-pass (короткий timeout) → enqueue sync на wake.

    Долгий per-binding IDLE в HTTP/worker process не держим: cron tick
    запускает supervisor; timeout ограничен, fairness по max_idle_bindings.
    """
    _ = schedule_task_id
    _ = company_id
    settings = get_settings()
    config = settings.mail_sync
    if not config.enabled or not config.idle_enabled:
        return {"idle_sessions": 0, "wakes": 0}
    candidates = await di.mail_service.list_sync_candidates(
        limit=config.max_idle_bindings,
        auth_error_cooldown_seconds=config.auth_error_cooldown_seconds,
    )
    filtered = [
        binding
        for binding in candidates
        if not (
            binding.kind == MailboxBindingKind.USER
            and (binding.user_id is None or not binding.user_id.strip())
        )
    ]
    # TaskIQ tick: не блокируем на 29 мин; короткий IDLE-window.
    timeout_seconds = float(min(60, config.idle_timeout_seconds))
    results = await asyncio.gather(
        *[
            _idle_one_binding(
                mail_service=di.mail_service,
                binding=binding,
                timeout_seconds=timeout_seconds,
            )
            for binding in filtered
        ]
    )
    wakes = sum(1 for woke in results if woke)
    return {"idle_sessions": len(filtered), "wakes": wakes}
