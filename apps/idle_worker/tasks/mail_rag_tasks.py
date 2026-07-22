"""TaskIQ: фоновая RAG-индексация писем (не блокирует IMAP persist)."""

from __future__ import annotations

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from apps.idle_worker.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from core.mail.service import stored_to_list_item
from core.types import JsonObject
from core.ui_events.dispatcher import publish_ui_event_to_user


async def _notify_users_for_binding(
    *,
    mailbox_binding_id: str,
    company_id: str,
    event_type: str,
    payload: JsonObject,
) -> None:
    container = get_container()
    bindings = await container.mailbox_binding_repository.list_by_company(company_id)
    binding = next(
        (item for item in bindings if item.mailbox_binding_id == mailbox_binding_id),
        None,
    )
    if binding is None:
        return
    user_ids: list[str] = []
    if binding.user_id is not None:
        user_ids.append(binding.user_id)
    members = await container.mailbox_binding_member_repository.list_for_binding(
        mailbox_binding_id
    )
    for member in members:
        if member.user_id not in user_ids:
            user_ids.append(member.user_id)
    for user_id in user_ids:
        await publish_ui_event_to_user(user_id, event_type, payload)


@idle_broker.task(task_name="mail_rag_index", queue_name="idle")
async def mail_rag_index_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> dict[str, str]:
    container = get_container()
    binding = await container.mailbox_binding_repository.get(
        mailbox_binding_id, company_id
    )
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    previous = await enter_mail_binding_context(
        container, binding, channel="mail_rag_index"
    )
    try:
        try:
            stored = await container.mail_service.index_mail_message(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
                company_id=company_id,
            )
        except Exception:
            failed = await container.mail_message_repository.get_by_uid(
                mailbox_binding_id,
                folder=folder,
                uid=int(uid),
            )
            if failed is not None:
                list_item = stored_to_list_item(failed)
                await _notify_users_for_binding(
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
