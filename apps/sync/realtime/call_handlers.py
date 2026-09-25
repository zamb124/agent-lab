"""Обработчики realtime-команд для WebRTC звонков.

События — PlatformEvent на шине; UI читает их с Centrifugo `/realtime`.
call.signal адресован одному получателю (`delivery.user_ids`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import aiohttp
from livekit.api.twirp_client import TwirpError, TwirpErrorCode

from apps.sync.di import Di
from apps.sync.events import (
    event_call_accepted,
    event_call_declined,
    event_call_ended,
    event_call_incoming,
    event_call_participant_joined,
    event_call_participant_left,
)
from apps.sync.models.call import SyncCall
from apps.sync.models.call_link import SyncCallLink
from apps.sync.models.call_participant import SyncCallParticipant
from apps.sync.models.calls import (
    CallMode,
    CallParticipantRead,
    CallRead,
    CallsAcceptPayload,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallStatus,
    ParticipantStatus,
)
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channels import ChannelType
from apps.sync.realtime.speech_to_chat_workflow import stop_speech_egresses_for_call_room
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.calls.livekit_client import LiveKitClient
from core.calls.livekit_usage_spans import trace_livekit_room_session_usage
from core.config import get_settings
from core.events.contract import PlatformEvent
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)


async def _call_event_recipients(
    channel_access: SyncChannelAccessService,
    *,
    channel_id: str,
) -> list[str]:
    return await channel_access.list_member_user_ids(channel_id)


# P2P сигналинг (RTCPeerConnection + offer/answer/ICE relay) не реализован на клиенте.
# Все звонки используют SFU через LiveKit.
# Когда P2P будет реализован — вернуть P2P_MAX = 2.
P2P_MAX = 0


def _call_mode(value: str) -> CallMode:
    if value == "p2p":
        return "p2p"
    if value == "sfu":
        return "sfu"
    raise ValueError(f"Unknown call mode: {value!r}")


def _call_status(value: str) -> CallStatus:
    if value == "ringing":
        return "ringing"
    if value == "active":
        return "active"
    if value == "ended":
        return "ended"
    raise ValueError(f"Unknown call status: {value!r}")


def _participant_status(value: str) -> ParticipantStatus:
    if value == "invited":
        return "invited"
    if value == "joined":
        return "joined"
    if value == "declined":
        return "declined"
    if value == "left":
        return "left"
    raise ValueError(f"Unknown participant status: {value!r}")


def call_read_from_entities(call: SyncCall, participants: list[SyncCallParticipant]) -> CallRead:
    return CallRead(
        call_id=call.call_id,
        channel_id=call.channel_id,
        mode=_call_mode(call.mode),
        call_type="video",
        status=_call_status(call.status),
        livekit_room_name=call.livekit_room_name,
        started_at=call.started_at,
        ended_at=call.ended_at,
        created_at=call.created_at,
        created_by_user_id=call.created_by_user_id,
        participants=[
            CallParticipantRead(
                user_id=p.user_id,
                status=_participant_status(p.status),
                joined_at=p.joined_at,
                left_at=p.left_at,
            )
            for p in sorted(participants, key=lambda participant: participant.user_id)
        ],
    )


async def handle_call_invite(
    payload: CallsInvitePayload,
    *,
    actor_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
    authz: AuthzService,
    resolve_user: bool = False,
) -> tuple[CallRead, list[PlatformEvent]]:
    """Создаёт звонок и событие call.incoming только для участников канала."""
    if not await authz.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=actor_user_id
    ):
        raise PermissionError("No access to channel.")

    existing = await SyncCall.find_open_in_channel(company_id, payload.channel_id)
    if existing is not None:
        now = datetime.now(UTC)
        await SyncCall.mark_call_status(existing.call_id, "ended", ended_at=now)
        for participant_row in await SyncCallParticipant.list_for_call(existing.call_id):
            if participant_row.status == "joined":
                await SyncCallParticipant.mark_call_participant_status(
                    existing.call_id,
                    participant_row.user_id,
                    "left",
                    left_at=now,
                )

    member_rows = await channel_access.list_member_rows(payload.channel_id)
    member_ids = [user_id for user_id, _role in member_rows]
    mode = "p2p" if len(member_ids) <= P2P_MAX else "sfu"

    livekit_room_name: str | None = None
    if mode == "sfu":
        settings = get_settings()
        lk = LiveKitClient(
            url=settings.calls.livekit_url,
            api_key=settings.calls.livekit_api_key,
            api_secret=settings.calls.livekit_api_secret,
        )
        persistent = await SyncCallLink.find_persistent_for_channel(
            company_id, payload.channel_id
        )
        if persistent is not None:
            # Та же комната, что у гостевой ссылки без call_id (join / op_calls_join_accept).
            livekit_room_name = f"link-{persistent.link_token[:16]}"
        else:
            livekit_room_name = f"call-{uuid4().hex}"
        await lk.create_room(
            livekit_room_name,
            company_id=company_id,
            user_id=actor_user_id,
        )

    call = SyncCall(
        call_id=uuid4().hex,
        company_id=company_id,
        channel_id=payload.channel_id,
        mode=mode,
        call_type="video",
        status="ringing",
        livekit_room_name=livekit_room_name,
        created_by_user_id=actor_user_id,
    )
    _ = await SyncCall.set(call)

    for uid in member_ids:
        participant = SyncCallParticipant(
            call_participant_id=uuid4().hex,
            call_id=call.call_id,
            user_id=uid,
            status="joined" if uid == actor_user_id else "invited",
            joined_at=datetime.now(UTC) if uid == actor_user_id else None,
        )
        _ = await SyncCallParticipant.set(participant)

    participants = await SyncCallParticipant.list_for_call(call.call_id)
    call_read = call_read_from_entities(call, participants)

    ch_entity = await SyncChannel.get(payload.channel_id)
    if ch_entity is None:
        raise ValueError(f"Channel {payload.channel_id} not found.")

    caller_display_name = actor_user_id
    if resolve_user:
        creator = await User.get(actor_user_id)
        if creator is not None:
            caller_display_name = creator.name
    channel_display_name: str | None = None
    if ch_entity.type != ChannelType.DIRECT.value:
        raw_name = ch_entity.name
        if isinstance(raw_name, str) and raw_name.strip() != "":
            channel_display_name = raw_name

    incoming = event_call_incoming(
        call_read,
        company_id=company_id,
        recipient_user_ids=member_ids,
        initiator_user_id=actor_user_id,
        caller_display_name=caller_display_name,
        incoming_channel_kind=ch_entity.type,
        channel_display_name=channel_display_name,
    )

    return call_read, [incoming]


async def handle_call_accept(
    payload: CallsAcceptPayload,
    *,
    actor_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
) -> tuple[CallRead, list[PlatformEvent], bool]:
    """Третий элемент: звонок только что перешёл ringing → active (для маркера в чате)."""
    call = await SyncCall.require_company_call(payload.call_id, company_id)

    if call.status == "ended":
        raise ValueError("Call is already ended.")

    was_ringing = call.status == "ringing"
    now = datetime.now(UTC)
    await SyncCallParticipant.mark_call_participant_status(
        payload.call_id,
        actor_user_id,
        "joined",
        joined_at=now,
    )

    active_count = await SyncCallParticipant.count_joined(payload.call_id)
    became_active = False
    if active_count >= 2 and call.status == "ringing":
        await SyncCall.mark_call_status(payload.call_id, "active", started_at=now)
        became_active = True

    participants = await SyncCallParticipant.list_for_call(payload.call_id)
    call_read = call_read_from_entities(
        await SyncCall.require_company_call(payload.call_id, company_id), participants
    )

    recipients = await _call_event_recipients(
        channel_access, channel_id=call.channel_id
    )
    return call_read, [
        event_call_accepted(
            payload.call_id,
            actor_user_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
        event_call_participant_joined(
            payload.call_id,
            actor_user_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
    ], bool(became_active and was_ringing)


async def handle_call_decline(
    payload: CallsDeclinePayload,
    *,
    actor_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
) -> tuple[CallRead, list[PlatformEvent]]:
    call = await SyncCall.require_company_call(payload.call_id, company_id)

    if call.status == "ended":
        raise ValueError("Call is already ended.")

    await SyncCallParticipant.mark_call_participant_status(
        payload.call_id, actor_user_id, "declined"
    )
    participants = await SyncCallParticipant.list_for_call(payload.call_id)
    call_read = call_read_from_entities(call, participants)

    recipients = await _call_event_recipients(
        channel_access, channel_id=call.channel_id
    )
    return call_read, [
        event_call_declined(
            payload.call_id,
            actor_user_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
    ]


async def handle_call_hangup(
    payload: CallsHangupPayload,
    *,
    actor_user_id: str,
    company_id: str,
    channel_access: SyncChannelAccessService,
    di: Di,
) -> tuple[CallRead, list[PlatformEvent], bool]:
    """Третий элемент: звонок полностью завершён (последний участник вышел)."""
    call = await SyncCall.require_company_call(payload.call_id, company_id)

    if call.status == "ended":
        raise ValueError("Call is already ended.")

    now = datetime.now(UTC)
    await SyncCallParticipant.mark_call_participant_status(
        payload.call_id,
        actor_user_id,
        "left",
        left_at=now,
    )

    participants = await SyncCallParticipant.list_for_call(payload.call_id)
    active_count = sum(1 for p in participants if p.status == "joined")

    recipients = await _call_event_recipients(
        channel_access, channel_id=call.channel_id
    )
    events: list[PlatformEvent] = [
        event_call_participant_left(
            payload.call_id,
            actor_user_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
    ]

    call_fully_ended = False
    if active_count == 0:
        await SyncCall.mark_call_status(payload.call_id, "ended", ended_at=now)
        if call.mode == "sfu" and call.livekit_room_name:
            await stop_speech_egresses_for_call_room(
                call_id=payload.call_id,
                company_id=company_id,
                room_name=call.livekit_room_name,
                actor_user_id=actor_user_id,
                di=di,
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
                    company_id=company_id,
                    user_id=actor_user_id,
                )
            except TwirpError as exc:
                if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
                    logger.warning("sync.livekit.delete_room.room.code", room=call.livekit_room_name, code=exc.code)
                else:
                    raise
            except aiohttp.ClientError as exc:
                raise RuntimeError(
                    f"LiveKit delete_room: aiohttp network error room={call.livekit_room_name}"
                ) from exc

        ended_call = await SyncCall.require_company_call(payload.call_id, company_id)
        if (
            ended_call.mode == "sfu"
            and ended_call.livekit_room_name is not None
            and ended_call.livekit_room_name != ""
        ):
            await trace_livekit_room_session_usage(
                company_id=company_id,
                user_id=ended_call.created_by_user_id,
                call_id=payload.call_id,
                livekit_room_name=ended_call.livekit_room_name,
                started_at=ended_call.started_at,
                ended_at=ended_call.ended_at,
            )
        final_participants = await SyncCallParticipant.list_for_call(payload.call_id)
        call_read = call_read_from_entities(ended_call, final_participants)
        events.append(
            event_call_ended(
                call_read,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        )
        call_fully_ended = True
    else:
        call_read = call_read_from_entities(call, participants)

    return call_read, events, call_fully_ended
