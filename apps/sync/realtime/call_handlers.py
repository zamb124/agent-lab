"""Обработчики realtime-команд для WebRTC звонков.

Все события публикуются через sync.realtime.events → /sync/ws (broadcast).
Клиент фильтрует по channel_id / target_user_id в payload.
notification_manager здесь не используется — call-события не платформенные уведомления.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from apps.sync.db.models import SyncCall, SyncCallParticipant
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.models.calls import CallParticipantRead, CallRead
from apps.sync.realtime.commands import (
    CallAcceptPayload,
    CallDeclinePayload,
    CallHangupPayload,
    CallInvitePayload,
    CommandEnvelope,
)
from apps.sync.realtime.events import (
    RealtimeEvent,
    event_call_accepted,
    event_call_declined,
    event_call_ended,
    event_call_incoming,
    event_call_participant_joined,
    event_call_participant_left,
)
from core.calls.livekit_client import LiveKitClient
from core.config import get_settings
from core.logging import get_logger

logger = get_logger(__name__)

# P2P сигналинг (RTCPeerConnection + offer/answer/ICE relay) не реализован на клиенте.
# Все звонки используют SFU через LiveKit.
# Когда P2P будет реализован — вернуть P2P_MAX = 2.
P2P_MAX = 0


def _call_read_from_entities(call: SyncCall, participants: list[SyncCallParticipant]) -> CallRead:
    return CallRead(
        call_id=call.call_id,
        channel_id=call.channel_id,
        mode=call.mode,
        call_type="video",
        status=call.status,
        livekit_room_name=call.livekit_room_name,
        started_at=call.started_at,
        ended_at=call.ended_at,
        created_at=call.created_at,
        created_by_user_id=call.created_by_user_id,
        participants=[
            CallParticipantRead(
                user_id=p.user_id,
                status=p.status,
                joined_at=p.joined_at,
                left_at=p.left_at,
            )
            for p in participants
        ],
    )


async def handle_call_invite(
    cmd: CommandEnvelope,
    calls: CallRepository,
    channels: ChannelRepository,
) -> tuple[CallRead, list[RealtimeEvent]]:
    """Создаёт звонок.

    Возвращает call.incoming как broadcast-событие для /sync/ws.
    Клиент фильтрует: показывает баннер только тем, кто не является инициатором.
    """
    payload = CallInvitePayload.model_validate(cmd.payload)

    if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
        raise PermissionError("Нет доступа к каналу.")

    existing = await calls.get_active_call_for_channel(payload.channel_id, cmd.company_id)
    if existing is not None:
        now = datetime.now(UTC)
        await calls.update_call_status(existing.call_id, "ended", ended_at=now)
        for p in await calls.list_participants(existing.call_id):
            if p.status == "joined":
                await calls.update_participant_status(existing.call_id, p.user_id, "left", left_at=now)

    member_ids = await channels.list_member_user_ids(payload.channel_id, company_id=cmd.company_id)
    mode = "p2p" if len(member_ids) <= P2P_MAX else "sfu"

    livekit_room_name: str | None = None
    if mode == "sfu":
        settings = get_settings()
        lk = LiveKitClient(
            url=settings.calls.livekit_url,
            api_key=settings.calls.livekit_api_key,
            api_secret=settings.calls.livekit_api_secret,
        )
        livekit_room_name = f"call-{uuid4().hex}"
        await lk.create_room(livekit_room_name)

    call = SyncCall(
        call_id=uuid4().hex,
        company_id=cmd.company_id,
        channel_id=payload.channel_id,
        mode=mode,
        call_type="video",
        status="ringing",
        livekit_room_name=livekit_room_name,
        created_by_user_id=cmd.actor_user_id,
    )
    await calls.create_call(call)

    for uid in member_ids:
        participant = SyncCallParticipant(
            id=uuid4().hex,
            call_id=call.call_id,
            user_id=uid,
            status="joined" if uid == cmd.actor_user_id else "invited",
            joined_at=datetime.now(UTC) if uid == cmd.actor_user_id else None,
        )
        await calls.add_participant(participant)

    participants = await calls.list_participants(call.call_id)
    call_read = _call_read_from_entities(call, participants)

    # Broadcast через sync.realtime.events → /sync/ws.
    # Payload содержит initiator_user_id — клиент не показывает баннер инициатору.
    incoming = event_call_incoming(call_read)
    incoming.payload["initiator_user_id"] = cmd.actor_user_id

    return call_read, [incoming]


async def handle_call_accept(
    cmd: CommandEnvelope,
    calls: CallRepository,
) -> tuple[CallRead, list[RealtimeEvent]]:
    payload = CallAcceptPayload.model_validate(cmd.payload)
    call = await calls.get_call(payload.call_id, cmd.company_id)

    if call.status == "ended":
        raise ValueError("Звонок уже завершён.")

    now = datetime.now(UTC)
    await calls.update_participant_status(
        payload.call_id, cmd.actor_user_id, "joined", joined_at=now
    )

    active_count = await calls.count_active_participants(payload.call_id)
    if active_count >= 2 and call.status == "ringing":
        await calls.update_call_status(payload.call_id, "active", started_at=now)

    participants = await calls.list_participants(payload.call_id)
    call_read = _call_read_from_entities(
        await calls.get_call(payload.call_id, cmd.company_id), participants
    )

    return call_read, [
        event_call_accepted(payload.call_id, cmd.actor_user_id),
        event_call_participant_joined(payload.call_id, cmd.actor_user_id),
    ]


async def handle_call_decline(
    cmd: CommandEnvelope,
    calls: CallRepository,
) -> tuple[CallRead, list[RealtimeEvent]]:
    payload = CallDeclinePayload.model_validate(cmd.payload)
    call = await calls.get_call(payload.call_id, cmd.company_id)

    if call.status == "ended":
        raise ValueError("Звонок уже завершён.")

    await calls.update_participant_status(payload.call_id, cmd.actor_user_id, "declined")
    participants = await calls.list_participants(payload.call_id)
    call_read = _call_read_from_entities(call, participants)

    return call_read, [event_call_declined(payload.call_id, cmd.actor_user_id)]


async def handle_call_hangup(
    cmd: CommandEnvelope,
    calls: CallRepository,
) -> tuple[CallRead, list[RealtimeEvent]]:
    payload = CallHangupPayload.model_validate(cmd.payload)
    call = await calls.get_call(payload.call_id, cmd.company_id)

    if call.status == "ended":
        raise ValueError("Звонок уже завершён.")

    now = datetime.now(UTC)
    await calls.update_participant_status(
        payload.call_id, cmd.actor_user_id, "left", left_at=now
    )

    participants = await calls.list_participants(payload.call_id)
    active_count = sum(1 for p in participants if p.status == "joined")

    events: list[RealtimeEvent] = [
        event_call_participant_left(payload.call_id, cmd.actor_user_id)
    ]

    if active_count == 0:
        await calls.update_call_status(payload.call_id, "ended", ended_at=now)
        if call.mode == "sfu" and call.livekit_room_name:
            settings = get_settings()
            lk = LiveKitClient(
                url=settings.calls.livekit_url,
                api_key=settings.calls.livekit_api_key,
                api_secret=settings.calls.livekit_api_secret,
            )
            try:
                await lk.delete_room(call.livekit_room_name)
            except Exception:
                logger.exception("Не удалось удалить LiveKit комнату %s", call.livekit_room_name)

        ended_call = await calls.get_call(payload.call_id, cmd.company_id)
        final_participants = await calls.list_participants(payload.call_id)
        call_read = _call_read_from_entities(ended_call, final_participants)
        events.append(event_call_ended(call_read))
    else:
        call_read = _call_read_from_entities(call, participants)

    return call_read, events
