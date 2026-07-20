"""TaskIQ: IMAP mutations после локального optimistic update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import IdleWorkerContainer, get_container
from apps.idle_worker.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from core.logging import get_logger
from core.mail.models import (
    MailboxBinding,
    MailMessageFlagPayload,
    MailMessageMovePayload,
    MailMessageStarPayload,
    MailSendPayload,
)
from core.types import JsonObject
from core.ui_events.dispatcher import publish_ui_event_to_user

logger = get_logger(__name__)

T = TypeVar("T")


async def _load_binding(
    container: IdleWorkerContainer,
    *,
    company_id: str,
    mailbox_binding_id: str,
) -> MailboxBinding:
    binding = await container.mailbox_binding_repository.get(
        mailbox_binding_id, company_id
    )
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    return binding


async def _with_mail_binding_context(
    *,
    company_id: str,
    mailbox_binding_id: str,
    op: Callable[[IdleWorkerContainer, MailboxBinding], Awaitable[T]],
) -> T:
    container = get_container()
    binding = await _load_binding(
        container,
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
    )
    previous = await enter_mail_binding_context(
        container, binding, channel="mail_mutation"
    )
    try:
        return await op(container, binding)
    finally:
        leave_mail_binding_context(previous)


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


@idle_broker.task(task_name="mail_mark_seen", queue_name="idle")
async def mail_mark_seen_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    async def _op(container: IdleWorkerContainer, binding: MailboxBinding) -> None:
        _ = binding
        _ = await container.mail_service.mark_message_seen(
            MailMessageFlagPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
            ),
            company_id=company_id,
        )

    await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        op=_op,
    )
    logger.info(
        "mail.mark_seen.done",
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        uid=uid,
    )


@idle_broker.task(task_name="mail_mark_unseen", queue_name="idle")
async def mail_mark_unseen_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    async def _op(container: IdleWorkerContainer, binding: MailboxBinding) -> None:
        _ = binding
        _ = await container.mail_service.mark_message_unseen(
            MailMessageFlagPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
            ),
            company_id=company_id,
        )

    await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        op=_op,
    )
    logger.info(
        "mail.mark_unseen.done",
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        uid=uid,
    )


@idle_broker.task(task_name="mail_send", queue_name="idle")
async def mail_send_task(
    *,
    company_id: str,
    payload: JsonObject,
) -> None:
    send_payload = MailSendPayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding):
        _ = binding
        return await container.mail_service.send_message(
            send_payload,
            company_id=company_id,
        )

    try:
        result = await _with_mail_binding_context(
            company_id=company_id,
            mailbox_binding_id=send_payload.mailbox_binding_id,
            op=_op,
        )
    except Exception as exc:
        await _notify_users_for_binding(
            mailbox_binding_id=send_payload.mailbox_binding_id,
            company_id=company_id,
            event_type="mail/message/send_failed",
            payload={
                "mailbox_binding_id": send_payload.mailbox_binding_id,
                "error_detail": str(exc),
            },
        )
        raise
    await _notify_users_for_binding(
        mailbox_binding_id=send_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/send_succeeded",
        payload={
            "mailbox_binding_id": send_payload.mailbox_binding_id,
            "message_id": result.message_id,
            "accepted": list(result.accepted),
        },
    )
    logger.info(
        "mail.send.done",
        company_id=company_id,
        mailbox_binding_id=send_payload.mailbox_binding_id,
        message_id=result.message_id,
    )


@idle_broker.task(task_name="mail_move", queue_name="idle")
async def mail_move_task(*, company_id: str, payload: JsonObject) -> None:
    move_payload = MailMessageMovePayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding):
        _ = binding
        return await container.mail_service.move_message(
            move_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=move_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        mailbox_binding_id=move_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_trash", queue_name="idle")
async def mail_trash_task(*, company_id: str, payload: JsonObject) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding):
        _ = binding
        return await container.mail_service.trash_message(
            flag_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_archive", queue_name="idle")
async def mail_archive_task(*, company_id: str, payload: JsonObject) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding):
        _ = binding
        return await container.mail_service.archive_message(
            flag_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_delete", queue_name="idle")
async def mail_delete_task(*, company_id: str, payload: JsonObject) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding) -> None:
        _ = binding
        _ = await container.mail_service.delete_message(
            flag_payload, company_id=company_id
        )

    await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/removed",
        payload={
            "mailbox_binding_id": flag_payload.mailbox_binding_id,
            "folder": flag_payload.folder,
            "uid": flag_payload.uid,
        },
    )


@idle_broker.task(task_name="mail_star", queue_name="idle")
async def mail_star_task(*, company_id: str, payload: JsonObject) -> None:
    star_payload = MailMessageStarPayload.model_validate(payload)

    async def _op(container: IdleWorkerContainer, binding: MailboxBinding):
        _ = binding
        return await container.mail_service.star_message(
            star_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        company_id=company_id,
        mailbox_binding_id=star_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        mailbox_binding_id=star_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/upserted",
        payload={
            "mailbox_binding_id": star_payload.mailbox_binding_id,
            "folder": star_payload.folder,
            "uid": result.uid,
            "flagged": result.flagged,
            "unread_delta": 0,
        },
    )
