"""Flows task: срабатывание email-триггеров по новым письмам ящика.

Продюсер — `mail_sync_tick` idle worker'а: после синхронизации ящика он ставит задачу
с письмами без байтов вложений (триггеру нужны только заголовки и текст), а исполнение
идёт в flows_worker — владельце runtime триггеров.
"""

from __future__ import annotations

from apps.flows.di import Di
from apps.flows.src.tasks.task_names import TASK_DISPATCH_EMAIL_TRIGGERS
from apps.flows.src.triggers.handlers.email import dispatch_email_triggers_for_messages
from core.mail.models import InboundMailMessage, MailboxBinding
from core.tasks import platform_task
from core.types import JsonObject


@platform_task(TASK_DISPATCH_EMAIL_TRIGGERS)
async def dispatch_email_triggers(
    *,
    company_id: str,
    mailbox_binding_id: str,
    messages: list[JsonObject],
    dedup_ttl_seconds: int,
    di: Di,
) -> int:
    binding = await MailboxBinding.find_in_company(company_id, mailbox_binding_id)
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    inbound = [InboundMailMessage.model_validate(message) for message in messages]
    return await dispatch_email_triggers_for_messages(
        redis_client=di.redis_client,
        shared_storage=di.shared_storage,
        binding=binding,
        messages=inbound,
        dedup_ttl_seconds=dedup_ttl_seconds,
    )
