"""API роутер для сообщений (Messages)."""

from fastapi import APIRouter, Depends

from apps.sync.container import get_sync_container
from apps.sync.models.common import PaginationRequest
from apps.sync.models.messages import MessageCreate, MessageRow
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.tasks import handle_command
from core.context import get_context

router = APIRouter()


@router.get("/{channel_id}/messages")
async def list_messages(
    channel_id: str,
    pagination: PaginationRequest = Depends(),
) -> list[MessageRow]:
    """Сообщения канала."""
    context = get_context()
    container = get_sync_container()
    messages = await container.message_repository.list_by_channel(
        channel_id, limit=pagination.limit,
        company_id=context.active_company.company_id,
    )
    return [
        MessageRow(
            id=m.message_id,
            channel_id=m.channel_id,
            thread_id=m.thread_id,
            parent_message_id=m.parent_message_id,
            sender_user_id=m.sender_user_id,
            status=m.status,
            sent_at=m.sent_at,
            edited_at=m.edited_at,
        )
        for m in messages
    ]


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
