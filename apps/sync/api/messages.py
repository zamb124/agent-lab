"""API роутер для сообщений (Messages)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncMessage
from apps.sync.models.common import PaginationRequest, UserBrief
from apps.sync.models.messages import MessageContentModel, MessageCreate, MessageRead, MessageStatus
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.context import get_context
from core.models.identity_models import User

router = APIRouter()


async def _message_read_from_entity(
    container,
    m: SyncMessage,
    users_by_id: dict[str, User],
) -> MessageRead:
    content_rows = await container.message_repository.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    u = users_by_id.get(m.sender_user_id)
    if u is None:
        sender = UserBrief(id=m.sender_user_id, display_name=m.sender_user_id, avatar_url=None)
    else:
        sender = UserBrief(id=m.sender_user_id, display_name=u.name, avatar_url=u.avatar_url)

    return MessageRead(
        id=m.message_id,
        channel_id=m.channel_id,
        thread_id=m.thread_id,
        parent_message_id=m.parent_message_id,
        sender=sender,
        status=MessageStatus(m.status),
        sent_at=m.sent_at,
        edited_at=m.edited_at,
        contents=contents,
    )


@router.get("/{channel_id}/messages")
async def list_messages(
    channel_id: str,
    pagination: PaginationRequest = Depends(),
) -> list[MessageRead]:
    """Сообщения канала: полная модель с отправителем и контентом (как в MessageRead / WS)."""
    context = get_context()
    container = get_sync_container()
    rows = await container.message_repository.list_by_channel(
        channel_id,
        limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    if not rows:
        return []

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await container.user_repository.get_many(user_ids)

    chronological = list(reversed(rows))
    return [await _message_read_from_entity(container, m, users_by_id) for m in chronological]


@router.post("/{channel_id}/messages", status_code=201)
async def send_message(channel_id: str, body: MessageCreate) -> dict:
    """Отправка сообщения через TaskIQ."""
    context = get_context()
    cmd = CommandEnvelope(
        id=__import__("uuid").uuid4().hex,
        actor_user_id=context.user.user_id,
        company_id=context.active_company.company_id,
        type="messages.send",
        payload={"channel_id": channel_id, "body": body.model_dump()},
    )
    task = await handle_command.kiq(cmd.model_dump())
    res = await task.wait_result(timeout=300.0)
    if res.is_err:
        raise RuntimeError(f"Command failed: {res.error}")
    return res.return_value["result"]
