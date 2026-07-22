"""Постановка mail mutation / drain / sync задач в idle queue без импорта apps."""

from __future__ import annotations

from typing import Final

from taskiq import AsyncBroker

from core.mail.task_names import (
    MAIL_ARCHIVE_TASK_NAME,
    MAIL_DELETE_TASK_NAME,
    MAIL_MARK_SEEN_TASK_NAME,
    MAIL_MARK_UNSEEN_TASK_NAME,
    MAIL_MOVE_TASK_NAME,
    MAIL_RAG_INDEX_TASK_NAME,
    MAIL_SEND_TASK_NAME,
    MAIL_STAR_TASK_NAME,
    MAIL_SYNC_BINDING_TASK_NAME,
    MAIL_SYNC_TICK_TASK_NAME,
    MAIL_TRASH_TASK_NAME,
)
from core.tasks.broker import create_broker
from core.tasks.kicker import kiq_task_name_with_context
from core.types import JsonObject

_IDLE_QUEUE: Final[str] = "idle"
_idle_kick_broker: AsyncBroker | None = None


def _idle_broker() -> AsyncBroker:
    global _idle_kick_broker
    if _idle_kick_broker is None:
        _idle_kick_broker = create_broker(queue_name=_IDLE_QUEUE, service_name="idle_worker")
    return _idle_kick_broker


async def enqueue_mail_mark_seen(
    *,
    company_id: str,
    mailbox_binding_id: str,
    folder: str,
    uid: str,
) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_MARK_SEEN_TASK_NAME,
        _idle_broker(),
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
    _ = await kiq_task_name_with_context(
        MAIL_MARK_UNSEEN_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        uid=uid,
        background_kind="mail_mutation",
    )


async def enqueue_mail_send(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_SEND_TASK_NAME,
        _idle_broker(),
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
    _ = await kiq_task_name_with_context(
        MAIL_SYNC_TICK_TASK_NAME,
        _idle_broker(),
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
    _ = await kiq_task_name_with_context(
        MAIL_SYNC_BINDING_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        background_kind="mail_sync_binding",
    )


async def enqueue_mail_move(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_MOVE_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_trash(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_TRASH_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_archive(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_ARCHIVE_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_delete(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_DELETE_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        payload=payload,
        background_kind="mail_mutation",
    )


async def enqueue_mail_star(*, company_id: str, payload: JsonObject) -> None:
    _ = await kiq_task_name_with_context(
        MAIL_STAR_TASK_NAME,
        _idle_broker(),
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
    _ = await kiq_task_name_with_context(
        MAIL_RAG_INDEX_TASK_NAME,
        _idle_broker(),
        company_id=company_id,
        mailbox_binding_id=mailbox_binding_id,
        folder=folder,
        uid=uid,
        background_kind="mail_rag_index",
    )
