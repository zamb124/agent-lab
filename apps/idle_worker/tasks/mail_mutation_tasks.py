"""TaskIQ: IMAP mutations после локального optimistic update."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from apps.idle_worker.di import Di
from apps.idle_worker.tasks.mail_job_context import (
    enter_mail_binding_context,
    leave_mail_binding_context,
)
from apps.idle_worker.tasks.mail_recipients import mailbox_recipient_user_ids
from core.events import publish_event_to_users
from core.logging import get_logger
from core.mail.events import MAIL_MESSAGE_UPSERTED
from core.mail.models import (
    MailboxBinding,
    MailMessageFlagPayload,
    MailMessageMovePayload,
    MailMessageStarPayload,
    MailSendPayload,
)
from core.mail.task_names import (
    MAIL_ARCHIVE,
    MAIL_DELETE,
    MAIL_MARK_SEEN,
    MAIL_MARK_UNSEEN,
    MAIL_MOVE,
    MAIL_SEND,
    MAIL_STAR,
    MAIL_TRASH,
)
from core.tasks import platform_task
from core.types import JsonObject

logger = get_logger(__name__)

T = TypeVar("T")


async def _load_binding(
    *,
    company_id: str,
    mailbox_binding_id: str,
) -> MailboxBinding:
    binding = await MailboxBinding.by_mailbox_binding_id(
        company_id, mailbox_binding_id
    )
    if binding is None:
        raise ValueError(f"mailbox_binding_id not found: {mailbox_binding_id}")
    return binding


async def _with_mail_binding_context(
    *,
    company_id: str,
    mailbox_binding_id: str,
    op: Callable[[Di, MailboxBinding], Awaitable[T]],
    di: Di,
) -> T:
    binding = await _load_binding(
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
    )
    previous = await enter_mail_binding_context(
        di.authz_service, binding, channel="mail_mutation"
    )
    try:
        return await op(di, binding)
    finally:
        leave_mail_binding_context(previous)


async def _notify_users_for_binding(
    *,
    mailbox_binding_id: str,
    company_id: str,
    event_type: str,
    payload: JsonObject,
    di: Di,
) -> None:
    bindings = await MailboxBinding.list_by_email_address_for_company(company_id)
    binding = next(
        (item for item in bindings if item.mailbox_binding_id == mailbox_binding_id),
        None,
    )
    if binding is None:
        return
    user_ids = await mailbox_recipient_user_ids(di.authz_service, binding)
    if not user_ids:
        return
    await publish_event_to_users(
        user_ids,
        event_type,
        payload,
        company_id=company_id,
    )


@platform_task(MAIL_MARK_SEEN)
async def mail_mark_seen_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
    di: Di,
) -> None:
    async def _op(di: Di, binding: MailboxBinding) -> None:
        _ = binding
        _ = await di.mail_service.mark_message_seen(
            MailMessageFlagPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
            ),
            company_id=company_id,
        )

    await _with_mail_binding_context(
        di=di,
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


@platform_task(MAIL_MARK_UNSEEN)
async def mail_mark_unseen_task(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
    di: Di,
) -> None:
    async def _op(di: Di, binding: MailboxBinding) -> None:
        _ = binding
        _ = await di.mail_service.mark_message_unseen(
            MailMessageFlagPayload(
                mailbox_binding_id=mailbox_binding_id,
                folder=folder,
                uid=uid,
            ),
            company_id=company_id,
        )

    await _with_mail_binding_context(
        di=di,
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


@platform_task(MAIL_SEND)
async def mail_send_task(
    *,
    company_id: str,
    payload: JsonObject,
    di: Di,
) -> None:
    send_payload = MailSendPayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding):
        _ = binding
        return await di.mail_service.send_message(
            send_payload,
            company_id=company_id,
        )

    try:
        result = await _with_mail_binding_context(
            di=di,
            company_id=company_id,
            mailbox_binding_id=send_payload.mailbox_binding_id,
            op=_op,
        )
    except Exception as exc:
        await _notify_users_for_binding(
            di=di,
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
        di=di,
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


@platform_task(MAIL_MOVE)
async def mail_move_task(*, company_id: str, payload: JsonObject, di: Di) -> None:
    move_payload = MailMessageMovePayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding):
        _ = binding
        return await di.mail_service.move_message(
            move_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        di=di,
        company_id=company_id,
        mailbox_binding_id=move_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        di=di,
        mailbox_binding_id=move_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@platform_task(MAIL_TRASH)
async def mail_trash_task(*, company_id: str, payload: JsonObject, di: Di) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding):
        _ = binding
        return await di.mail_service.trash_message(
            flag_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        di=di,
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        di=di,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@platform_task(MAIL_ARCHIVE)
async def mail_archive_task(*, company_id: str, payload: JsonObject, di: Di) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding):
        _ = binding
        return await di.mail_service.archive_message(
            flag_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        di=di,
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        di=di,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/moved",
        payload=result.model_dump(mode="json"),
    )


@platform_task(MAIL_DELETE)
async def mail_delete_task(*, company_id: str, payload: JsonObject, di: Di) -> None:
    flag_payload = MailMessageFlagPayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding) -> None:
        _ = binding
        _ = await di.mail_service.delete_message(
            flag_payload, company_id=company_id
        )

    await _with_mail_binding_context(
        di=di,
        company_id=company_id,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        di=di,
        mailbox_binding_id=flag_payload.mailbox_binding_id,
        company_id=company_id,
        event_type="mail/message/removed",
        payload={
            "mailbox_binding_id": flag_payload.mailbox_binding_id,
            "folder": flag_payload.folder,
            "uid": flag_payload.uid,
        },
    )


@platform_task(MAIL_STAR)
async def mail_star_task(*, company_id: str, payload: JsonObject, di: Di) -> None:
    star_payload = MailMessageStarPayload.model_validate(payload)

    async def _op(di: Di, binding: MailboxBinding):
        _ = binding
        return await di.mail_service.star_message(
            star_payload, company_id=company_id
        )

    result = await _with_mail_binding_context(
        di=di,
        company_id=company_id,
        mailbox_binding_id=star_payload.mailbox_binding_id,
        op=_op,
    )
    await _notify_users_for_binding(
        di=di,
        mailbox_binding_id=star_payload.mailbox_binding_id,
        company_id=company_id,
        event_type=MAIL_MESSAGE_UPSERTED,
        payload={
            "mailbox_binding_id": star_payload.mailbox_binding_id,
            "folder": star_payload.folder,
            "uid": result.uid,
            "flagged": result.flagged,
            "unread_delta": 0,
        },
    )
