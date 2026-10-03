"""Внутренние helpers Sync.

Это внутренняя библиотека функций (`send_message`, …),
которыми пользуются `op_*` из `apps/sync/realtime/operations.py`. Никаких
веток `if cmd.type == ...` и никаких `CommandEnvelope` / `execute_command`
здесь нет — единый pipeline команд живёт в `operations.py`.
"""

from __future__ import annotations

from apps.sync.channel_read_helpers import channel_read_entity_minimal
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channels import ChannelRead
from apps.sync.realtime.task_names import (
    SYNC_SPEECH_TO_CHAT_POLL,
)
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.logging import get_logger
from core.tasks import enqueue

logger = get_logger(__name__)


async def channel_recipient_user_ids(
    channel_access: SyncChannelAccessService,
    channel_id: str,
) -> list[str]:
    return await channel_access.list_member_user_ids(channel_id)


async def maybe_start_speech_to_chat_poll(
    *,
    call_id: str,
    company_id: str,
    channel_id: str,
    livekit_room_name: str | None,
) -> None:
    if livekit_room_name is None or livekit_room_name == "":
        return
    ch = await SyncChannel.get(channel_id)
    if ch is None:
        raise ValueError(f"Channel {channel_id} not found.")
    if not ch.speech_to_chat_enabled:
        return
    _ = await enqueue(
        SYNC_SPEECH_TO_CHAT_POLL,
        call_id=call_id,
        company_id=company_id,
        background_kind="sync_call",
    )


def channel_read_entity(entity: SyncChannel) -> ChannelRead:
    return channel_read_entity_minimal(entity)
