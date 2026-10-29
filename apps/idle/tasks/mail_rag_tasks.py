"""TaskIQ: фоновая RAG-индексация писем (не блокирует IMAP persist)."""

from __future__ import annotations

from apps.idle.di import Di
from apps.idle.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from apps.idle.tasks.mail_recipients import mailbox_recipient_user_ids
from core.events import publish_event_to_users
from core.mail.models import MailboxBinding, StoredMailMessage
from core.mail.service import stored_to_list_item
from core.mail.task_names import MAIL_RAG_INDEX
from core.tasks import platform_task
from core.types import JsonObject


async def _notify_users_for_binding(
    *,
    mailbox_binding_id: str,
    company_id: str,
    event_type: str,
    payload: JsonObject,
    di: Di,
) -> None:
    bindings = await MailboxBinding.list_for_company_by_email_address_asc(company_id)
    binding = next(
        (item for item in bindings if item.mailbox_binding_id == mailbox_binding_id),
        None,
    )
    if binding is None:
        return
    user_ids = await mailbox_recipient_user_ids(di.authz_service, binding)
    if len(user_ids) == 0:
        return
    await publish_event_to_users(user_ids, event_type, payload)


@platform_task(MAIL_RAG_INDEX)
async def mail_rag_index_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
    di: Di,
) -> dict[str, str]:
    binding = await MailboxBinding.by_mailbox_binding_id(
        company_id, mailbox_binding_id
    )
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    previous = await enter_mail_binding_context(
        di.authz_service, binding, channel="mail_rag_index"
    )
    try:
        try:
            stored = await di.mail_service.index_mail_message(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
                company_id=company_id,
            )
        except Exception:
            failed = await StoredMailMessage.by_binding_folder_uid(
                mailbox_binding_id,
                folder=folder,
                uid=int(uid),
            )
            if failed is not None:
                list_item = stored_to_list_item(failed)
                await _notify_users_for_binding(
                    di=di,
                    mailbox_binding_id=mailbox_binding_id,
                    company_id=company_id,
                    event_type="mail/message/upserted",
                    payload={
                        "mailbox_binding_id": mailbox_binding_id,
                        "folder": folder,
                        "uid": uid,
                        "thread_id": failed.thread_id,
                        "list_item": list_item.model_dump(mode="json"),
                        "unread_delta": 0,
                        "flagged": failed.flagged,
                    },
                )
            raise
        list_item = stored_to_list_item(stored)
        await _notify_users_for_binding(
            di=di,
            mailbox_binding_id=mailbox_binding_id,
            company_id=company_id,
            event_type="mail/message/upserted",
            payload={
                "mailbox_binding_id": mailbox_binding_id,
                "folder": folder,
                "uid": uid,
                "thread_id": stored.thread_id,
                "list_item": list_item.model_dump(mode="json"),
                "unread_delta": 0,
                "flagged": stored.flagged,
            },
        )
        return {
            "mailbox_binding_id": mailbox_binding_id,
            "folder": folder,
            "uid": uid,
            "rag_index_status": stored.rag_index_status.value,
        }
    finally:
        leave_mail_binding_context(previous)
