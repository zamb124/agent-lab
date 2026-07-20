"""TaskIQ: IMAP mutations после локального optimistic update."""

from __future__ import annotations

from apps.idle_worker.broker import broker as idle_broker
from apps.idle_worker.container import get_container
from core.logging import get_logger
from core.mail.models import (
    MailMessageFlagPayload,
    MailMessageMovePayload,
    MailMessageStarPayload,
    MailSendPayload,
)
from core.types import JsonObject
from core.ui_events.dispatcher import publish_ui_event_to_user

logger = get_logger(__name__)


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
    container = get_container()
    _ = await container.mail_service.mark_message_seen(
        MailMessageFlagPayload(
            mailbox_binding_id=mailbox_binding_id,
            folder=folder,
            uid=uid,
        ),
        company_id=company_id,
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
    container = get_container()
    _ = await container.mail_service.mark_message_unseen(
        MailMessageFlagPayload(
            mailbox_binding_id=mailbox_binding_id,
            folder=folder,
            uid=uid,
        ),
        company_id=company_id,
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
    container = get_container()
    send_payload = MailSendPayload.model_validate(payload)
    try:
        result = await container.mail_service.send_message(
            send_payload,
            company_id=company_id,
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
    container = get_container()
    move_payload = MailMessageMovePayload.model_validate(payload)
    result = await container.mail_service.move_message(
        move_payload, company_id=company_id
    )
    await _notify_users_for_binding(
        mailbox_binding_id=move_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_trash", queue_name="idle")
async def mail_trash_task(*, company_id: str, payload: JsonObject) -> None:
    container = get_container()
    flag_payload = MailMessageFlagPayload.model_validate(payload)
    result = await container.mail_service.trash_message(
        flag_payload, company_id=company_id
    )
    await _notify_users_for_binding(
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_archive", queue_name="idle")
async def mail_archive_task(*, company_id: str, payload: JsonObject) -> None:
    container = get_container()
    flag_payload = MailMessageFlagPayload.model_validate(payload)
    result = await container.mail_service.archive_message(
        flag_payload, company_id=company_id
    )
    await _notify_users_for_binding(
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@idle_broker.task(task_name="mail_delete", queue_name="idle")
async def mail_delete_task(*, company_id: str, payload: JsonObject) -> None:
    container = get_container()
    flag_payload = MailMessageFlagPayload.model_validate(payload)
    _ = await container.mail_service.delete_message(
        flag_payload, company_id=company_id
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
    container = get_container()
    star_payload = MailMessageStarPayload.model_validate(payload)
    result = await container.mail_service.star_message(
        star_payload, company_id=company_id
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
