"""Постановка mail mutation / drain / sync задач в очередь ``idle``.

Единый ``enqueue`` сам резолвит брокер очереди; импорт apps не требуется.
"""

from __future__ import annotations

from core.mail.task_names import (
    MAIL_ARCHIVE,
    MAIL_DELETE,
    MAIL_MARK_SEEN,
    MAIL_MARK_UNSEEN,
    MAIL_MOVE,
    MAIL_RAG_INDEX,
    MAIL_SEND,
    MAIL_STAR,
    MAIL_SYNC_BINDING,
    MAIL_SYNC_TICK,
    MAIL_TRASH,
)
from core.tasks import enqueue
from core.types import JsonObject


async def enqueue_mail_mark_seen(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    _ = await enqueue(
        MAIL_MARK_SEEN,
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        uid=uid,
        background_kind="mail_mutation",
    )


async def enqueue_mail_mark_unseen(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    _ = await enqueue(
        MAIL_MARK_UNSEEN,
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        uid=uid,
        background_kind="mail_mutation",
    )


async def enqueue_mail_send(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_SEND,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_sync_tick_continuation(
    *,
    schedule_task_id: str | None,
    company_id: str | None,
    drain_depth: int,
) -> None:
    _ = await enqueue(
        MAIL_SYNC_TICK,
        schedule_task_id=schedule_task_id,
        company_id=company_id,
        drain_depth=drain_depth,
        background_kind="mail_sync_drain",
    )


async def enqueue_mail_sync_binding(
    *,
    company_id: str,
    mailbox_binding_id: str,
) -> None:
    _ = await enqueue(
        MAIL_SYNC_BINDING,
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        background_kind="mail_sync_binding",
    )


async def enqueue_mail_move(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_MOVE,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_trash(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_TRASH,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_archive(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_ARCHIVE,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_delete(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_DELETE,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_star(*, company_id: str, payload: JsonObject) -> None:
    _ = await enqueue(
        MAIL_STAR,
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_rag_index(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    _ = await enqueue(
        MAIL_RAG_INDEX,
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        uid=uid,
        background_kind="mail_rag_index",
    )
