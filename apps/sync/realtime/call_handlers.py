"""Обработчики realtime-команд для WebRTC звонков.

События публикуются в Redis и доходят до /sync/ws только участникам канала (и call.signal — адресно).
notification_manager здесь не используется — call-события не платформенные уведомления.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import aiohttp
from livekit.api.twirp_client import TwirpError, TwirpErrorCode

from apps.sync.db.models import SyncCall, SyncCallParticipant
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.models.calls import CallParticipantRead, CallRead
from apps.sync.models.channels import ChannelType
from apps.sync.realtime.commands import (
    CallAcceptPayload,
    CallDeclinePayload,
    CallHangupPayload,
    CallInvitePayload,
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
from core.db.repositories.user_repository import UserRepository
from core.logging import get_logger

logger = get_logger(__name__)


async def _call_event_recipients(
    channels: ChannelRepository,
    *,
    channel_id: str,
    company_id: str,
) -> list[str]:
    return await channels.list_member_user_ids(channel_id, company_id=company_id)


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
    cmd: Any,
    calls: CallRepository,
    channels: ChannelRepository,
    user_repository: UserRepository | None = None,
) -> tuple[CallRead, list[RealtimeEvent]]:
    """Создаёт звонок и событие call.incoming только для участников канала."""
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
        await lk.create_room(
            livekit_room_name,
            company_id=cmd.company_id,
            user_id=cmd.actor_user_id,
        )

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

    incoming = event_call_incoming(
        call_read,
        company_id=cmd.company_id,
        recipient_user_ids=member_ids,
    )
    incoming.payload["initiator_user_id"] = cmd.actor_user_id

    ch_entity = await channels.get(payload.channel_id)
    if ch_entity is None:
        raise ValueError(f"Канал {payload.channel_id} не найден.")

    caller_display_name = cmd.actor_user_id
    if user_repository is not None:
        creator = await user_repository.get(cmd.actor_user_id)
        if creator is not None:
            caller_display_name = creator.name
    incoming.payload["caller_display_name"] = caller_display_name
    incoming.payload["incoming_channel_kind"] = ch_entity.type
    if ch_entity.type != ChannelType.DIRECT.value:
        raw_name = ch_entity.name
        if isinstance(raw_name, str) and raw_name.strip() != "":
            incoming.payload["channel_display_name"] = raw_name

    return call_read, [incoming]


async def handle_call_accept(
    cmd: Any,
    calls: CallRepository,
    channels: ChannelRepository,
) -> tuple[CallRead, list[RealtimeEvent], bool]:
    """Третий элемент: звонок только что перешёл ringing → active (для маркера в чате)."""
    payload = CallAcceptPayload.model_validate(cmd.payload)
    call = await calls.get_call(payload.call_id, cmd.company_id)

    if call.status == "ended":
        raise ValueError("Звонок уже завершён.")

    was_ringing = call.status == "ringing"
    now = datetime.now(UTC)
    await calls.update_participant_status(
        payload.call_id, cmd.actor_user_id, "joined", joined_at=now
    )

    active_count = await calls.count_active_participants(payload.call_id)
    became_active = False
    if active_count >= 2 and call.status == "ringing":
        await calls.update_call_status(payload.call_id, "active", started_at=now)
        became_active = True

    participants = await calls.list_participants(payload.call_id)
    call_read = _call_read_from_entities(
        await calls.get_call(payload.call_id, cmd.company_id), participants
    )

    recipients = await _call_event_recipients(
        channels, channel_id=call.channel_id, company_id=cmd.company_id
    )
    return call_read, [
        event_call_accepted(
            payload.call_id,
            cmd.actor_user_id,
            company_id=cmd.company_id,
            recipient_user_ids=recipients,
        ),
        event_call_participant_joined(
            payload.call_id,
            cmd.actor_user_id,
            company_id=cmd.company_id,
            recipient_user_ids=recipients,
        ),
    ], bool(became_active and was_ringing)


async def handle_call_decline(
    cmd: Any,
    calls: CallRepository,
    channels: ChannelRepository,
) -> tuple[CallRead, list[RealtimeEvent]]:
    payload = CallDeclinePayload.model_validate(cmd.payload)
    call = await calls.get_call(payload.call_id, cmd.company_id)

    if call.status == "ended":
        raise ValueError("Звонок уже завершён.")

    await calls.update_participant_status(payload.call_id, cmd.actor_user_id, "declined")
    participants = await calls.list_participants(payload.call_id)
    call_read = _call_read_from_entities(call, participants)

    recipients = await _call_event_recipients(
        channels, channel_id=call.channel_id, company_id=cmd.company_id
    )
    return call_read, [
        event_call_declined(
            payload.call_id,
            cmd.actor_user_id,
            company_id=cmd.company_id,
            recipient_user_ids=recipients,
        ),
    ]


async def handle_call_hangup(
    cmd: Any,
    calls: CallRepository,
    channels: ChannelRepository,
) -> tuple[CallRead, list[RealtimeEvent], bool]:
    """Третий элемент: звонок полностью завершён (последний участник вышел)."""
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

    recipients = await _call_event_recipients(
        channels, channel_id=call.channel_id, company_id=cmd.company_id
    )
    events: list[RealtimeEvent] = [
        event_call_participant_left(
            payload.call_id,
            cmd.actor_user_id,
            company_id=cmd.company_id,
            recipient_user_ids=recipients,
        ),
    ]

    call_fully_ended = False
    if active_count == 0:
        await calls.update_call_status(payload.call_id, "ended", ended_at=now)
        if call.mode == "sfu" and call.livekit_room_name:
            from apps.sync.realtime.speech_to_chat_workflow import stop_speech_egresses_for_call_room

            await stop_speech_egresses_for_call_room(
                call_id=payload.call_id,
                company_id=cmd.company_id,
                room_name=call.livekit_room_name,
                actor_user_id=cmd.actor_user_id,
            )
            settings = get_settings()
            lk = LiveKitClient(
                url=settings.calls.livekit_url,
                api_key=settings.calls.livekit_api_key,
                api_secret=settings.calls.livekit_api_secret,
            )
            try:
                await lk.delete_room(
                    call.livekit_room_name,
                    company_id=cmd.company_id,
                    user_id=cmd.actor_user_id,
                )
            except TwirpError as exc:
                if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
                    logger.warning(
                        "LiveKit delete_room: комната уже отсутствует room=%s code=%s",
                        call.livekit_room_name,
                        exc.code,
                    )
                else:
                    raise
            except aiohttp.ClientError as exc:
                raise RuntimeError(
                    f"LiveKit delete_room: сетевая ошибка aiohttp room={call.livekit_room_name}"
                ) from exc

        ended_call = await calls.get_call(payload.call_id, cmd.company_id)
        final_participants = await calls.list_participants(payload.call_id)
        call_read = _call_read_from_entities(ended_call, final_participants)
        events.append(
            event_call_ended(
                call_read,
                company_id=cmd.company_id,
                recipient_user_ids=recipients,
            ),
        )
        call_fully_ended = True
    else:
        call_read = _call_read_from_entities(call, participants)

    return call_read, events, call_fully_ended
