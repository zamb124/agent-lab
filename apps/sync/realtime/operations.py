"""Единый реестр операций Sync — один handler, два транспорта.

Контракт:
    async def op_<entity>_<verb>(
        payload: <Op>Payload,
        *,
        user: User,
        di: Di,
    ) -> <Op>Result | None

Для каждой операции:
  - REST-route в `apps/sync/api/**` валидирует входное тело через Pydantic
    (FastAPI), вызывает `op_*` напрямую и сериализует результат.
  - WS command-handler (`core.websocket.register_service_operations`)
    валидирует payload через тот же Pydantic-класс и вызывает ту же `op_*`.

Zero-fallback canon (см. `main.mdc`):
  - Никаких `or default` / `getattr(payload, k, default)` — поля валидирует
    Pydantic, отсутствие = `ValidationError` → `WsCommandError("ws_invalid_payload", ...)`.
  - Никаких `try/except Exception` вокруг repository-вызовов. IO-ошибки
    идут наверх как 500.
  - Бизнес-инварианты: явный `raise WsCommandError(code, detail)`.
    Не «вернуть пустой результат».
  - `require_company` бросает, если контекста нет, — никаких неявных
    дефолтов на `system` или `user.active_company_id`.

Mutating-операции исполняются in-process. TaskIQ — только для явно
помеченных heavy-операций (`messages.transcribe_audio/video/call`),
запускаемых через `enqueue(SPEC, ...)` внутри `op_*` после валидации/обновления
статуса.
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.constants import CHANNEL_TYPE_CALENDAR_MEETING
from apps.sync.di import Di
from apps.sync.events import (
    MessageStatusChangedPayload,
    event_call_admin_changed,
    event_call_recording_started,
    event_call_recording_stopped,
    event_call_signal,
    event_channel_created,
    event_channel_member_added,
    event_channel_pins_changed,
    event_channel_read_updated,
    event_channel_typing,
    event_git_resource_upserted,
    event_message_created,
    event_message_deleted,
    event_message_reaction_changed,
    event_message_status_changed,
    event_message_updated,
    event_thread_created,
)
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.call import SyncCall
from apps.sync.models.call_link import SyncCallLink
from apps.sync.models.call_participant import SyncCallParticipant
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkPatch,
    CallLinkRead,
    CallRead,
    CallsAcceptPayload,
    CallScheduledLinkRead,
    CallsDeclinePayload,
    CallsHangupPayload,
    CallsInvitePayload,
    CallsSignalPayload,
    GuestJoinRequest,
    JoinResponse,
)
from apps.sync.models.channel import (
    SyncChannel,
    SyncChannelMember,
)
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberRead,
    ChannelMemberRole,
    ChannelRead,
    ChannelUpdate,
)
from apps.sync.models.common import UserBrief
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.models.git import (
    GitProvider,
    GitResourceKind,
    GitResourceRef,
    GitResourceRefCreate,
    GitResourceRefRead,
)
from apps.sync.models.meetings import CallRecordingRead, SyncCallRecording
from apps.sync.models.message import SyncMessage, SyncMessageContent
from apps.sync.models.messages import (
    CallBoundaryContent,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    MessageRead,
    MessageStatus,
    ReactionEntry,
)
from apps.sync.models.threads import SyncThread, ThreadCreate, ThreadRead, ThreadRow
from apps.sync.realtime.call_handlers import (
    call_read_from_entities,
    handle_call_accept,
    handle_call_decline,
    handle_call_hangup,
    handle_call_invite,
)
from apps.sync.realtime.handlers import (
    build_livekit_recording_client,
    channel_read_entity,
    channel_recipient_user_ids,
    create_channel,
    create_thread,
    maybe_start_speech_to_chat_poll,
    message_read_from_db,
    normalize_s3_egress_endpoint,
    send_message,
    send_message_with_side_effects,
    set_audio_transcription_state,
    set_video_transcription_state,
    stop_and_finalize_recording,
    update_channel,
    upsert_git_resource,
)
from apps.sync.realtime.livekit_sdk_boundary import read_livekit_egress_id
from apps.sync.realtime.task_names import (
    SYNC_AGGREGATE_CALL_TRANSCRIPT,
    SYNC_TRANSCRIBE_AUDIO_MESSAGE,
    SYNC_TRANSCRIBE_VIDEO_MESSAGE,
)
from apps.sync.sender_display import sender_brief_for_message
from apps.sync.ws_presence import batch_peer_presence
from core.authz.models import AuthzCheckItem, AuthzObject, AuthzSubject
from core.authz.types import AuthzRelation
from core.calls.livekit_client import LiveKitClient
from core.calls.models import TurnCredentials
from core.calls.turn import generate_turn_credentials
from core.config import BaseSettings, get_settings
from core.events import publish_events
from core.events.contract import PlatformEvent
from core.files.create_spec import FileSourceKind
from core.files.file_ref import FileRef, stored_file_ref
from core.files.models import AudioTranscriptionStatus, FileRecord
from core.files.object_store.gate import FileGate
from core.logging import get_logger
from core.models.identity_models import Company, User
from core.pagination import CursorPage, ListResponse, OffsetPage
from core.platform_brand.resolver import resolve_context_host, resolve_livekit_public_url
from core.request_scope import require_company
from core.short_links.models import PlatformShortLink
from core.tasks import enqueue
from core.types import JsonObject, parse_json_object
from core.websocket import WsCommandError

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Кодирование cursor (общий формат для cursor списка messages через WS и REST)
# ---------------------------------------------------------------------------


def _encode_message_cursor(*, sent_at: datetime, message_id: str) -> str:
    payload = {"sent_at": sent_at.isoformat(), "message_id": message_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_message_cursor(cursor: str) -> tuple[datetime, str]:
    padded = cursor + ("=" * ((4 - len(cursor) % 4) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = parse_json_object(raw, "message cursor")
    except (ValueError, UnicodeDecodeError) as exc:
        raise WsCommandError("ws_invalid_cursor", "cursor must be base64url(JSON)", error_code='ws_invalid_cursor') from exc
    sent_at_raw = payload.get("sent_at")
    message_id = payload.get("message_id")
    if not isinstance(sent_at_raw, str) or not sent_at_raw:
        raise WsCommandError("ws_invalid_cursor", "cursor.sent_at required", error_code='ws_invalid_cursor')
    if not isinstance(message_id, str) or not message_id:
        raise WsCommandError("ws_invalid_cursor", "cursor.message_id required", error_code='ws_invalid_cursor')
    try:
        sent_at = datetime.fromisoformat(sent_at_raw)
    except ValueError as exc:
        raise WsCommandError("ws_invalid_cursor", "cursor.sent_at must be ISO datetime", error_code='ws_invalid_cursor') from exc
    return sent_at, message_id


# ===========================================================================
# Каналы
# ===========================================================================


class ChannelsListPayload(BaseModel):
    namespace: str | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ChannelsUpdatePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    body: ChannelUpdate


class ChannelsMarkReadPayload(BaseModel):
    channel_id: str = Field(min_length=1)


class ChannelsTypingPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    typing: bool
    thread_id: str | None = Field(default=None)


class ChannelsNotificationSettingsUpdatePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    notifications_muted: bool


class ChannelsAddMemberPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    role: ChannelMemberRole = "member"


class ChannelsListMembersPayload(BaseModel):
    channel_id: str = Field(min_length=1)


async def _build_channel_read(
    di: Di,
    channel: SyncChannel,
    *,
    viewer_id: str,
    company_id: str,
) -> ChannelRead:
    summaries = await SyncMessage.channel_lane_summaries(
        company_id=company_id,
        channel_ids=[channel.channel_id],
        viewer_user_id=viewer_id,
    )
    return await channel_read_from_entity(
        channel,
        viewer_user_id=viewer_id,
        channel_access=di.channel_access_service,
        resolve_user=True,
        company_id=company_id,
        lane_summary=summaries[channel.channel_id],
    )


async def _filter_channels_by_can_view(
    di: Di,
    channels: list[SyncChannel],
    *,
    user_id: str,
    peer_user_id: str | None = None,
) -> list[SyncChannel]:
    """SQL settings-rows — кандидаты; ACL — только FGA can_view."""
    if not channels:
        return []
    checks: list[AuthzCheckItem] = [
        AuthzCheckItem(
            subject=AuthzSubject.user(user_id),
            relation=AuthzRelation.CAN_VIEW,
            obj=AuthzObject.sync_channel(channel.channel_id),
            correlation_id=channel.channel_id,
        )
        for channel in channels
    ]
    if peer_user_id is not None:
        checks.extend(
            AuthzCheckItem(
                subject=AuthzSubject.user(peer_user_id),
                relation=AuthzRelation.CAN_VIEW,
                obj=AuthzObject.sync_channel(channel.channel_id),
                correlation_id=f"peer:{channel.channel_id}",
            )
            for channel in channels
        )
    allowed = await di.authz_service.batch_check(checks)
    if peer_user_id is None:
        return [
            channel
            for channel, ok in zip(channels, allowed, strict=True)
            if ok
        ]
    viewer_flags = allowed[: len(channels)]
    peer_flags = allowed[len(channels) :]
    return [
        channel
        for channel, viewer_ok, peer_ok in zip(
            channels, viewer_flags, peer_flags, strict=True
        )
        if viewer_ok and peer_ok
    ]


async def op_channels_list(
    payload: ChannelsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ChannelRead]:
    company_id = require_company().company_id
    candidates = await SyncChannel.list_channels_for_user(
        user.user_id,
        namespace=payload.namespace,
        limit=payload.limit,
        offset=payload.offset,
        company_id=company_id,
    )
    channels = await _filter_channels_by_can_view(
        di, candidates, user_id=user.user_id
    )
    channel_ids = [c.channel_id for c in channels]
    summaries = await SyncMessage.channel_lane_summaries(
        company_id=company_id,
        channel_ids=channel_ids,
        viewer_user_id=user.user_id,
    )
    items: list[ChannelRead] = []
    for c in channels:
        items.append(
            await channel_read_from_entity(
                c,
                viewer_user_id=user.user_id,
                channel_access=di.channel_access_service,
                resolve_user=True,
                company_id=company_id,
                lane_summary=summaries[c.channel_id],
            )
        )
    return OffsetPage[ChannelRead](
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


async def op_channels_create(
    payload: ChannelCreate,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    channel, created_new = await create_channel(
        payload,
        actor_user_id=user.user_id,
        company_id=company_id,
        channel_access=di.channel_access_service,
        namespaces=di.namespace_service,
    )
    if created_new:
        recipients = await channel_recipient_user_ids(
            di.channel_access_service, channel.channel_id
        )
        await publish_events(
            [
                event_channel_created(
                    channel, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
    return channel


async def op_channels_update(
    payload: ChannelsUpdatePayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    return await update_channel(
        payload.channel_id,
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
        authz=di.authz_service,
    )


async def op_channels_mark_read(
    payload: ChannelsMarkReadPayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError(
            "forbidden", f"User is not a member of channel {payload.channel_id}.",
                  error_code='forbidden',
              )
    max_at = await SyncMessage.max_root_lane_sent_at(
        payload.channel_id, company_id=company_id
    )
    read_at = max_at if max_at is not None else datetime.now(UTC)
    await SyncChannelMember.set_channel_member_last_read_at(
        payload.channel_id,
        user.user_id,
        read_at,
        company_id=company_id,
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_channel_read_updated(
                payload.channel_id,
                user.user_id,
                read_at,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        ]
    )
    return None


async def op_channels_typing(
    payload: ChannelsTypingPayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError(
            "forbidden", f"User is not a member of channel {payload.channel_id}.",
                  error_code='forbidden',
              )
    if payload.thread_id is not None and payload.thread_id != "":
        thread = await SyncThread.get(payload.thread_id)
        if thread is None:
            raise WsCommandError("not_found", f"Thread {payload.thread_id} not found.", error_code='not_found')
        if thread.company_id != company_id:
            raise WsCommandError("forbidden", "Thread does not belong to the company.", error_code='forbidden')
        if thread.channel_id != payload.channel_id:
            raise WsCommandError("forbidden", "Thread does not belong to the given channel.", error_code='forbidden')
    user_obj = await User.get(user.user_id)
    if user_obj is None:
        raise WsCommandError("not_found", f"User {user.user_id} not found.", error_code='not_found')
    user_brief = UserBrief(
        user_id=user.user_id, display_name=user_obj.name, avatar_url=user_obj.avatar_url
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_channel_typing(
                channel_id=payload.channel_id,
                thread_id=payload.thread_id if payload.thread_id else None,
                typing=payload.typing,
                user=user_brief,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        ]
    )
    return None


async def op_channels_notification_settings_update(
    payload: ChannelsNotificationSettingsUpdatePayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    ch = await SyncChannel.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    await SyncChannelMember.set_channel_member_notifications_muted(
        payload.channel_id,
        user.user_id,
        payload.notifications_muted,
        company_id=company_id,
    )
    return await _build_channel_read(
        di, ch, viewer_id=user.user_id, company_id=company_id
    )


async def op_channels_add_member(
    payload: ChannelsAddMemberPayload,
    *,
    user: User,
    di: Di,
) -> ChannelMemberRead:
    company_id = require_company().company_id
    ch = await SyncChannel.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
    if not await di.authz_service.can_admin(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No permission to manage channel members.", error_code='forbidden')
    await SyncChannelMember.ensure_channel_member_row(
        payload.channel_id,
        payload.user_id,
        company_id=company_id,
    )
    try:
        await di.channel_access_service.set_member(
            payload.channel_id,
            user_id=payload.user_id,
            relation=payload.role,
        )
    except Exception:
        _ = await SyncChannelMember.delete_channel_member(
            payload.channel_id,
            payload.user_id,
            company_id=company_id,
        )
        raise
    recipients = await di.channel_access_service.list_member_user_ids(
        payload.channel_id
    )
    await publish_events(
        [
            event_channel_member_added(
                payload.channel_id,
                payload.user_id,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        ]
    )
    return ChannelMemberRead(user_id=payload.user_id, role=payload.role)


async def op_channels_list_members(
    payload: ChannelsListMembersPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[ChannelMemberRead]:
    company_id = require_company().company_id
    ch = await SyncChannel.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    rows = await di.channel_access_service.list_member_rows(payload.channel_id)
    return ListResponse[ChannelMemberRead](
        items=[ChannelMemberRead(user_id=uid, role=role) for uid, role in rows]
    )


# ===========================================================================
# Треды
# ===========================================================================


class ThreadsListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ThreadsItemPayload(BaseModel):
    thread_id: str = Field(min_length=1)


class ThreadsCreatePayload(BaseModel):
    body: ThreadCreate


async def op_threads_list(
    payload: ThreadsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ThreadRow]:
    _ = user
    _ = di
    company_id = require_company().company_id
    threads = await SyncThread.list_threads_in_channel(
        company_id,
        payload.channel_id,
        limit=payload.limit,
        offset=payload.offset,
    )
    items = [ThreadRow.model_validate(thread.model_dump()) for thread in threads]
    return OffsetPage[ThreadRow](
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


async def op_threads_item(
    payload: ThreadsItemPayload,
    *,
    user: User,
    di: Di,
) -> ThreadRow:
    _ = user
    _ = di
    _ = require_company()
    thread = await SyncThread.get(payload.thread_id)
    if thread is None:
        raise WsCommandError("not_found", f"Thread {payload.thread_id!r} not found.", error_code='not_found')
    return ThreadRow.model_validate(thread.model_dump())


async def op_threads_create(
    payload: ThreadsCreatePayload,
    *,
    user: User,
    di: Di,
) -> ThreadRead:
    company_id = require_company().company_id
    thread = await create_thread(
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
        resolve_user=True,
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, thread.channel_id
    )
    await publish_events(
        [
            event_thread_created(
                thread, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return thread


# ===========================================================================
# Сообщения
# ===========================================================================


class MessagesListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    before: str | None = Field(default=None)
    after: str | None = Field(default=None)


async def _listed_message_sender_brief(
    users_by_id: dict[str, User],
    sender_user_id: str,
) -> UserBrief:
    u = users_by_id.get(sender_user_id)
    if u is None:
        return await sender_brief_for_message(sender_user_id, resolve_user=False)
    return UserBrief(
        user_id=sender_user_id, display_name=u.name, avatar_url=u.avatar_url
    )


class MessagesSendPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    body: MessageCreate


class MessagesEditPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    body: MessageEdit


class MessagesDeletePayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesForwardPayload(BaseModel):
    from_channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    to_channel_id: str = Field(min_length=1)
    thread_id: str | None = Field(default=None)


class MessagesReactPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    emoji: str | None = Field(default=None)


class MessagesPinPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    action: Literal["add", "remove"]


class MessagesMarkReadPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeAudioPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeVideoPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)


class MessagesTranscribeCallPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    call_id: str = Field(min_length=1)


class MessagesTranscribeCallResult(BaseModel):
    status: Literal["queued"] = "queued"


async def op_messages_list(
    payload: MessagesListPayload,
    *,
    user: User,
    di: Di,
) -> CursorPage[MessageRead]:
    _ = user
    _ = di
    company_id = require_company().company_id
    if payload.before is not None and payload.after is not None:
        raise WsCommandError(
            "ws_invalid_payload", "before and after are mutually exclusive",
                  error_code='ws_invalid_payload',
              )

    before_sent_at: datetime | None = None
    before_message_id: str | None = None
    if payload.before is not None and payload.before != "":
        before_sent_at, before_message_id = _decode_message_cursor(payload.before)
    after_sent_at: datetime | None = None
    after_message_id: str | None = None
    if payload.after is not None and payload.after != "":
        after_sent_at, after_message_id = _decode_message_cursor(payload.after)

    window = await SyncMessage.list_root_lane_cursor(
        channel_id=payload.channel_id,
        limit=payload.limit,
        before_sent_at=before_sent_at,
        before_message_id=before_message_id,
        after_sent_at=after_sent_at,
        after_message_id=after_message_id,
        company_id=company_id,
    )
    rows = window.rows
    if not rows:
        return CursorPage[MessageRead](
            items=[], next_cursor=None, prev_cursor=None, has_more=False,
        )

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await User.get_many(user_ids)

    chronological = list(reversed(rows))
    items: list[MessageRead] = []
    for m in chronological:
        contents = await SyncMessageContent.list_for_message(m.message_id)
        sender = await _listed_message_sender_brief(users_by_id, m.sender_user_id)
        items.append(message_read_from_entity(m=m, contents=contents, sender=sender))

    oldest = chronological[0]
    newest = chronological[-1]
    next_cursor = (
        _encode_message_cursor(sent_at=oldest.sent_at, message_id=oldest.message_id)
        if window.has_more_older
        else None
    )
    prev_cursor = (
        _encode_message_cursor(sent_at=newest.sent_at, message_id=newest.message_id)
        if window.has_more_newer
        else None
    )
    return CursorPage[MessageRead](
        items=items,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
        has_more=window.has_more_older,
    )


class MessagesListThreadPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_messages_list_thread(
    payload: MessagesListThreadPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[MessageRead]:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "Not a channel member", error_code='forbidden')
    thread = await SyncThread.get(payload.thread_id)
    if thread is None:
        raise WsCommandError("not_found", f"Thread {payload.thread_id!r} not found.", error_code='not_found')
    if thread.channel_id != payload.channel_id:
        raise WsCommandError(
            "ws_invalid_payload",
            "thread_id does not belong to channel_id",
                  error_code='ws_invalid_payload',
              )
    rows = await SyncMessage.list_by_thread(
        thread_id=payload.thread_id,
        limit=payload.limit,
        offset=payload.offset,
        company_id=company_id,
    )
    if not rows:
        return OffsetPage[MessageRead](
            items=[],
            total=0,
            limit=payload.limit,
            offset=payload.offset,
        )
    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await User.get_many(user_ids)
    items: list[MessageRead] = []
    for m in rows:
        contents = await SyncMessageContent.list_for_message(m.message_id)
        sender = await _listed_message_sender_brief(users_by_id, m.sender_user_id)
        items.append(message_read_from_entity(m=m, contents=contents, sender=sender))
    return OffsetPage[MessageRead](
        items=items,
        total=len(items),
        limit=payload.limit,
        offset=payload.offset,
    )


async def op_messages_send(
    payload: MessagesSendPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    return await send_message_with_side_effects(
        channel_id=payload.channel_id,
        body=payload.body,
        user=user,
        di=di,
    )


async def op_messages_mark_read(
    payload: MessagesMarkReadPayload,
    *,
    user: User,
    di: Di,
) -> None:
    _ = user
    company_id = require_company().company_id
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_message_status_changed(
                payload.channel_id,
                MessageStatusChangedPayload(
                    message_id=payload.message_id, status=MessageStatus.READ
                ),
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        ]
    )
    return None


async def op_messages_edit(
    payload: MessagesEditPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    m = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
    if m.sender_user_id != user.user_id:
        raise WsCommandError("forbidden", "Only the author can edit.", error_code='forbidden')
    edited_at = datetime.now(tz=UTC)
    await SyncMessage.replace_contents(
        payload.message_id, payload.body.contents, edited_at
    )
    m2 = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m2 is None:
        raise WsCommandError("internal", "Message disappeared after edit.", error_code='internal')
    read = await message_read_from_db(
        m2, resolve_user=True
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_message_updated(
                read, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return read


async def op_messages_delete(
    payload: MessagesDeletePayload,
    *,
    user: User,
    di: Di,
) -> MessagesDeletePayload:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    m = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if m.sender_user_id != user.user_id and not await di.authz_service.check(
        AuthzSubject.user(user.user_id),
        AuthzRelation.OWNER,
        AuthzObject.sync_channel(payload.channel_id),
    ):
        raise WsCommandError("forbidden", "Insufficient permission to delete.", error_code='forbidden')
    now = datetime.now(tz=UTC)
    await SyncMessage.soft_delete(payload.message_id, now)
    ch = await SyncChannel.get(payload.channel_id)
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    events: list[PlatformEvent] = [
        event_message_deleted(
            payload.channel_id,
            payload.message_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
    ]
    if ch is not None:
        pids = list(ch.pinned_message_ids)
        if payload.message_id in pids:
            new_pids = [x for x in pids if x != payload.message_id]
            await SyncChannel.set_channel_pinned_message_ids(
                payload.channel_id,
                new_pids,
                company_id=company_id,
            )
            ch2 = await SyncChannel.get(payload.channel_id)
            if ch2 is not None:
                events.append(
                    event_channel_pins_changed(
                        channel_read_entity(ch2),
                        company_id=company_id,
                        recipient_user_ids=recipients,
                    ),
                )
    await publish_events(events)
    return payload


async def op_messages_forward(
    payload: MessagesForwardPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.from_channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the source channel.", error_code='forbidden')
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.to_channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the target channel.", error_code='forbidden')
    m = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if m.channel_id != payload.from_channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Cannot forward a deleted message.", error_code='forbidden')
    contents = await SyncMessageContent.list_for_message(m.message_id)
    body = MessageCreate(
        thread_id=payload.thread_id,
        parent_message_id=None,
        contents=contents,
    )
    src_ch = await SyncChannel.get(payload.from_channel_id)
    if src_ch is None:
        raise WsCommandError("not_found", "Source channel not found.", error_code='not_found')
    raw_name = src_ch.name
    fwd_label = (
        raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() != "" else None
    )
    new_read = await send_message(
        payload.to_channel_id,
        body,
        actor_user_id=user.user_id,
        company_id=company_id,
        resolve_user=True,
        forwarded_from_channel_id=payload.from_channel_id,
        forwarded_from_channel_name=fwd_label,
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.to_channel_id
    )
    dst_ch = await SyncChannel.get(payload.to_channel_id)
    if dst_ch is None:
        raise WsCommandError("not_found", "Target channel not found.", error_code='not_found')
    await publish_events(
        [
            event_message_created(
                new_read,
                company_id=company_id,
                recipient_user_ids=recipients,
                channel_type=dst_ch.type,
            ),
        ]
    )
    return new_read


def _apply_reaction_json(
    reactions_raw: list[JsonObject],
    actor_user_id: str,
    emoji: str | None,
    now: datetime,
) -> list[ReactionEntry]:
    filtered: list[ReactionEntry] = []
    for reaction_payload in reactions_raw:
        reaction = ReactionEntry.model_validate(reaction_payload)
        if reaction.user_id != actor_user_id:
            filtered.append(reaction)
    if emoji is None:
        return filtered
    filtered.append(
        ReactionEntry(user_id=actor_user_id, emoji=emoji, created_at=now)
    )
    return filtered


async def op_messages_react(
    payload: MessagesReactPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    m = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
    now = datetime.now(tz=UTC)
    new_reactions = _apply_reaction_json(m.reactions, user.user_id, payload.emoji, now)
    await SyncMessage.set_reactions(payload.message_id, new_reactions)
    m2 = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m2 is None:
        raise WsCommandError("internal", "Message disappeared after reaction.", error_code='internal')
    read = await message_read_from_db(
        m2, resolve_user=True
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_message_reaction_changed(
                payload.channel_id,
                payload.message_id,
                new_reactions,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
            event_message_updated(
                read, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return read


async def op_messages_pin(
    payload: MessagesPinPayload,
    *,
    user: User,
    di: Di,
) -> ChannelRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    if not await di.authz_service.check(
        AuthzSubject.user(user.user_id),
        AuthzRelation.OWNER,
        AuthzObject.sync_channel(payload.channel_id),
    ):
        raise WsCommandError("forbidden", "Only the channel owner can pin.", error_code='forbidden')
    m = await SyncMessage.find_in_company(company_id, payload.message_id)
    if m is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Cannot pin a deleted message.", error_code='forbidden')
    ch = await SyncChannel.get(payload.channel_id)
    if ch is None:
        raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
    pids = list(ch.pinned_message_ids)
    if payload.action == "add":
        if payload.message_id not in pids:
            pids.insert(0, payload.message_id)
    else:
        pids = [x for x in pids if x != payload.message_id]
    await SyncChannel.set_channel_pinned_message_ids(
        payload.channel_id,
        pids,
        company_id=company_id,
    )
    ch2 = await SyncChannel.get(payload.channel_id)
    if ch2 is None:
        raise WsCommandError("internal", "Channel disappeared after update.", error_code='internal')
    cr = channel_read_entity(ch2)
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_channel_pins_changed(
                cr, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return cr


async def op_messages_transcribe_audio(
    payload: MessagesTranscribeAudioPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    source = await SyncMessage.find_in_company(
        company_id, payload.message_id
    )
    if source is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if source.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if source.deleted_at is not None:
        raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
    source_contents = await SyncMessageContent.list_for_message(payload.message_id)
    try:
        processing_contents = set_audio_transcription_state(
            source_contents,
            status=AudioTranscriptionStatus.PROCESSING,
            transcription_text=None,
            transcription_error=None,
        )
    except ValueError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc), error_code='ws_invalid_payload') from exc
    edited_at = datetime.now(tz=UTC)
    await SyncMessage.replace_contents(
        payload.message_id, processing_contents, edited_at
    )
    updated_entity = await SyncMessage.find_in_company(
        company_id, payload.message_id
    )
    if updated_entity is None:
        raise WsCommandError("internal", "Message disappeared after transcription start.", error_code='internal')
    updated_read = await message_read_from_db(
        updated_entity, resolve_user=True
    )
    _ = await enqueue(
        SYNC_TRANSCRIBE_AUDIO_MESSAGE,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        background_kind="sync_transcribe",
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_message_updated(
                updated_read, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return updated_read


async def op_messages_transcribe_video(
    payload: MessagesTranscribeVideoPayload,
    *,
    user: User,
    di: Di,
) -> MessageRead:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    source = await SyncMessage.find_in_company(
        company_id, payload.message_id
    )
    if source is None:
        raise WsCommandError("not_found", "Message not found.", error_code='not_found')
    if source.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
    if source.deleted_at is not None:
        raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
    source_contents = await SyncMessageContent.list_for_message(payload.message_id)
    try:
        processing_contents = set_video_transcription_state(
            source_contents,
            status=AudioTranscriptionStatus.PROCESSING,
            transcription_text=None,
            transcription_error=None,
        )
    except ValueError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc), error_code='ws_invalid_payload') from exc
    edited_at = datetime.now(tz=UTC)
    await SyncMessage.replace_contents(
        payload.message_id, processing_contents, edited_at
    )
    updated_entity = await SyncMessage.find_in_company(
        company_id, payload.message_id
    )
    if updated_entity is None:
        raise WsCommandError("internal", "Message disappeared after transcription start.", error_code='internal')
    updated_read = await message_read_from_db(
        updated_entity, resolve_user=True
    )
    _ = await enqueue(
        SYNC_TRANSCRIBE_VIDEO_MESSAGE,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        background_kind="sync_transcribe",
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, payload.channel_id
    )
    await publish_events(
        [
            event_message_updated(
                updated_read, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return updated_read


async def op_messages_transcribe_call(
    payload: MessagesTranscribeCallPayload,
    *,
    user: User,
    di: Di,
) -> MessagesTranscribeCallResult:
    company_id = require_company().company_id
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(payload.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    if call.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "call_id does not belong to this channel.", error_code='forbidden')
    _ = await enqueue(
        SYNC_AGGREGATE_CALL_TRANSCRIPT,
        channel_id=payload.channel_id,
        call_id=payload.call_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        background_kind="sync_transcribe",
    )
    return MessagesTranscribeCallResult(status="queued")


# ===========================================================================
# Git-ресурсы
# ===========================================================================


class GitResourcesUpsertPayload(BaseModel):
    body: GitResourceRefCreate


class GitResourcesGetPayload(BaseModel):
    git_ref_id: str = Field(min_length=1)


async def op_git_resources_upsert(
    payload: GitResourcesUpsertPayload,
    *,
    user: User,
    di: Di,
) -> GitResourceRefRead:
    _ = user
    _ = di
    company_id = require_company().company_id
    ref = await upsert_git_resource(
        payload.body, company_id=company_id
    )
    await publish_events([event_git_resource_upserted(ref, company_id=company_id)])
    return ref


async def op_git_resources_get(
    payload: GitResourcesGetPayload,
    *,
    user: User,
    di: Di,
) -> GitResourceRefRead:
    _ = user
    _ = di
    _ = require_company()
    ref = await GitResourceRef.get(payload.git_ref_id)
    if ref is None:
        raise WsCommandError("not_found", "Git resource not found", error_code='not_found')
    return GitResourceRefRead(
        git_ref_id=ref.git_ref_id,
        provider=GitProvider(ref.provider),
        kind=GitResourceKind(ref.kind),
        project_key=ref.project_key,
        external_id=ref.external_id,
        url=ref.url,
        extra=ref.extra,
    )


# ===========================================================================
# Звонки (изменяющие WS-команды)
# ===========================================================================


class CallsRecordingStartPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingStopPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsAdminTransferPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)


async def _post_call_boundary_message_op(
    *,
    channel_id: str,
    call_id: str,
    phase: Literal["started", "ended"],
    sender_user_id: str,
    company_id: str,
) -> MessageRead:
    if phase == "ended":
        recordings = await SyncCallRecording.list_for_call(call_id, company_id)
        has_recording = any(r.status == "uploaded" for r in recordings)
        boundary_data = CallBoundaryContent(
            call_id=call_id, phase=phase, has_recording=has_recording
        )
    else:
        boundary_data = CallBoundaryContent(call_id=call_id, phase=phase)

    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.CALL_BOUNDARY,
                data=boundary_data,
                order=0,
            )
        ],
        mentioned_user_ids=None,
        call_id=call_id,
    )
    return await send_message(
        channel_id,
        body,
        actor_user_id=sender_user_id,
        company_id=company_id,
        resolve_user=True,
    )


async def op_calls_invite(
    payload: CallsInvitePayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    try:
        out, evs = await handle_call_invite(
            payload,
            actor_user_id=user.user_id,
            company_id=company_id,
            channel_access=di.channel_access_service,
            authz=di.authz_service,
            resolve_user=True,
        )
    except PermissionError as exc:
        raise WsCommandError("forbidden", str(exc), error_code='forbidden') from exc
    member_rows = await di.channel_access_service.list_member_rows(out.channel_id)
    member_ids = [uid for uid, _role in member_rows]
    started_read = await _post_call_boundary_message_op(
        channel_id=out.channel_id,
        call_id=out.call_id,
        phase="started",
        sender_user_id=out.created_by_user_id,
        company_id=company_id,
    )
    invite_channel = await SyncChannel.get(out.channel_id)
    if invite_channel is None:
        raise WsCommandError("not_found", f"Channel {out.channel_id} not found.", error_code='not_found')
    evs.append(
        event_message_created(
            started_read,
            company_id=company_id,
            recipient_user_ids=member_ids,
            channel_type=invite_channel.type,
        ),
    )
    if len(member_ids) <= 1:
        now = datetime.now(UTC)
        await SyncCall.mark_call_status(out.call_id, "active", started_at=now)
        solo_call = await SyncCall.require_company_call(out.call_id, company_id)
        await maybe_start_speech_to_chat_poll(
            call_id=solo_call.call_id,
            company_id=company_id,
            channel_id=solo_call.channel_id,
            livekit_room_name=solo_call.livekit_room_name,
        )
    await publish_events(evs)
    return out


async def op_calls_accept(
    payload: CallsAcceptPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    try:
        out, evs, became_active = await handle_call_accept(
            payload,
            actor_user_id=user.user_id,
            company_id=company_id,
            channel_access=di.channel_access_service,
        )
    except ValueError as exc:
        raise WsCommandError("conflict", str(exc), error_code='conflict') from exc
    if became_active:
        await maybe_start_speech_to_chat_poll(
            call_id=out.call_id,
            company_id=company_id,
            channel_id=out.channel_id,
            livekit_room_name=out.livekit_room_name,
        )
    await publish_events(evs)
    return out


async def op_calls_decline(
    payload: CallsDeclinePayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    try:
        out, evs = await handle_call_decline(
            payload,
            actor_user_id=user.user_id,
            company_id=company_id,
            channel_access=di.channel_access_service,
        )
    except ValueError as exc:
        raise WsCommandError("conflict", str(exc), error_code='conflict') from exc
    await publish_events(evs)
    return out


async def op_calls_hangup(
    payload: CallsHangupPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id

    auto_stopped_recording_event: PlatformEvent | None = None
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    active_recording = await SyncCallRecording.active_for_call(
        payload.call_id, company_id
    )
    if active_recording is not None and active_recording.started_by_user_id == user.user_id:
        stopped_recording = await stop_and_finalize_recording(
            call=call,
            recording=active_recording,
            company_id=company_id,
            actor_user_id=user.user_id,
        )
        rec_stop_recipients = await channel_recipient_user_ids(
            di.channel_access_service, call.channel_id
        )
        auto_stopped_recording_event = event_call_recording_stopped(
            stopped_recording, company_id=company_id, recipient_user_ids=rec_stop_recipients
        )

    try:
        out, evs, fully_ended = await handle_call_hangup(
            payload,
            actor_user_id=user.user_id,
            company_id=company_id,
            channel_access=di.channel_access_service,
            di=di,
        )
    except ValueError as exc:
        raise WsCommandError("conflict", str(exc), error_code='conflict') from exc
    if auto_stopped_recording_event is not None:
        evs.append(auto_stopped_recording_event)
    if fully_ended:
        boundary_read = await _post_call_boundary_message_op(
            channel_id=out.channel_id,
            call_id=out.call_id,
            phase="ended",
            sender_user_id=out.created_by_user_id,
            company_id=company_id,
        )
        recipients = await channel_recipient_user_ids(
            di.channel_access_service, out.channel_id
        )
        hangup_channel = await SyncChannel.get(out.channel_id)
        if hangup_channel is None:
            raise WsCommandError("not_found", f"Channel {out.channel_id} not found.", error_code='not_found')
        evs.append(
            event_message_created(
                boundary_read,
                company_id=company_id,
                recipient_user_ids=recipients,
                channel_type=hangup_channel.type,
            ),
        )
    await publish_events(evs)
    return out


async def op_calls_recording_start(
    payload: CallsRecordingStartPayload,
    *,
    user: User,
    di: Di,
) -> CallRecordingRead:
    company_id = require_company().company_id
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    if call.status == "ended":
        raise WsCommandError("forbidden", "Cannot start recording for an ended call.", error_code='forbidden')
    if call.created_by_user_id != user.user_id:
        raise WsCommandError("forbidden", "Only the meeting admin can start recording.", error_code='forbidden')
    if call.livekit_room_name is None or call.livekit_room_name == "":
        raise WsCommandError(
            "forbidden", f"Call {call.call_id} has no livekit_room_name.",
                  error_code='forbidden',
              )
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the call.", error_code='forbidden')
    active = await SyncCallRecording.active_for_call(payload.call_id, company_id)
    if active is not None:
        raise WsCommandError("forbidden", "Recording is already running.", error_code='forbidden')

    channel_entity = await SyncChannel.get(call.channel_id)
    if channel_entity is None:
        raise WsCommandError("not_found", f"Channel {call.channel_id} not found.", error_code='not_found')
    settings = get_settings()
    if settings.recording_max_duration_seconds <= 0:
        raise WsCommandError("internal", "recording_max_duration_seconds must be greater than 0.", error_code='internal')
    if not settings.s3.enabled:
        raise WsCommandError("internal", "S3 is disabled: call recording to S3 is unavailable.", error_code='internal')
    try:
        egress_target = await FileGate().egress_target(
            company_id,
            FileSourceKind.SYNC_CALL_RECORDING,
        )
    except Exception as exc:
        raise WsCommandError(
            "internal",
            f"S3 egress target resolution failed: {exc}",
            error_code="internal",
        ) from exc
    recording_id = uuid4().hex
    egress_filepath = (
        f"sync-recordings/{company_id}/{call.call_id}/{recording_id}.mp4"
    )
    livekit_client = build_livekit_recording_client()
    await livekit_client.create_room(
        call.livekit_room_name, company_id=company_id, user_id=user.user_id
    )
    egress_info = await livekit_client.start_room_composite_egress_to_s3(
        room_name=call.livekit_room_name,
        filepath=egress_filepath,
        s3_access_key=egress_target.access_key_id,
        s3_secret_key=egress_target.secret_access_key,
        s3_region=egress_target.region_name,
        s3_bucket=egress_target.bucket_name,
        company_id=company_id,
        user_id=user.user_id,
        s3_endpoint=normalize_s3_egress_endpoint(egress_target.endpoint_url),
        audio_only=(call.call_type == "audio"),
    )
    provider_job_id = read_livekit_egress_id(egress_info)
    logger.info(
        "call.recording.start",
        call_id=call.call_id,
        recording_id=recording_id,
        room=call.livekit_room_name,
        egress_id=provider_job_id,
        audio_only=call.call_type == 'audio',
    )
    recording = SyncCallRecording(
        recording_id=recording_id,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=call.channel_id,
        namespace=channel_entity.namespace,
        status="recording",
        started_by_user_id=user.user_id,
        provider_job_id=provider_job_id,
        storage_id=egress_target.storage_id,
        started_at=datetime.now(UTC),
    )
    _ = await SyncCallRecording.set(recording)
    out = CallRecordingRead.model_validate(recording.model_dump())
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, call.channel_id
    )
    await publish_events(
        [
            event_call_recording_started(
                out, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return out


async def op_calls_recording_stop(
    payload: CallsRecordingStopPayload,
    *,
    user: User,
    di: Di,
) -> CallRecordingRead:
    company_id = require_company().company_id
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the call.", error_code='forbidden')
    active = await SyncCallRecording.active_for_call(payload.call_id, company_id)
    if active is None:
        raise WsCommandError("not_found", "Active recording not found.", error_code='not_found')
    is_meeting_admin = call.created_by_user_id == user.user_id
    is_recording_starter = active.started_by_user_id == user.user_id
    if not is_meeting_admin and not is_recording_starter:
        raise WsCommandError(
            "forbidden",
            "Only the meeting admin or the user who started recording can stop it.",
                  error_code='forbidden',
              )
    out = await stop_and_finalize_recording(
        call=call,
        recording=active,
        company_id=company_id,
        actor_user_id=user.user_id,
    )
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, call.channel_id
    )
    await publish_events(
        [
            event_call_recording_stopped(
                out, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return out


async def op_calls_admin_transfer(
    payload: CallsAdminTransferPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    company_id = require_company().company_id
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    if call.created_by_user_id != user.user_id:
        raise WsCommandError(
            "forbidden", "Only the current meeting admin can transfer admin.",
                  error_code='forbidden',
              )
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the call.", error_code='forbidden')
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=payload.target_user_id
    ):
        raise WsCommandError("forbidden", "New admin is not a channel member.", error_code='forbidden')
    if payload.target_user_id.startswith("guest:"):
        raise WsCommandError("forbidden", "Cannot assign a guest as meeting admin.", error_code='forbidden')
    participants = await SyncCallParticipant.list_for_call(call.call_id)
    target_participant = next(
        (item for item in participants if item.user_id == payload.target_user_id), None
    )
    if target_participant is None:
        raise WsCommandError("not_found", "New admin is not among call participants.", error_code='not_found')
    if target_participant.status != "joined":
        raise WsCommandError(
            "forbidden", "New admin must be an active call participant.",
                  error_code='forbidden',
              )
    await SyncCall.assign_admin(call.call_id, payload.target_user_id)
    updated_call = await SyncCall.require_company_call(call.call_id, company_id)
    updated_participants = await SyncCallParticipant.list_for_call(call.call_id)
    out = call_read_from_entities(updated_call, updated_participants)
    recipients = await channel_recipient_user_ids(
        di.channel_access_service, out.channel_id
    )
    await publish_events(
        [
            event_call_admin_changed(
                out, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return out


async def op_calls_signal(
    payload: CallsSignalPayload,
    *,
    user: User,
    di: Di,
) -> None:
    """Быстрый путь сигналинга: без TaskIQ, прямая публикация события."""
    _ = di
    company_id = require_company().company_id
    event = event_call_signal(
        payload.call_id,
        payload.signal_type,
        payload.data,
        company_id=company_id,
        recipient_user_ids=[payload.target_user_id],
        target_user_id=payload.target_user_id,
        sender_user_id=user.user_id,
    )
    await publish_events([event])
    return None


# ===========================================================================
# Звонки (чтение + ссылки + join)
# ===========================================================================


class CallsGetPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingsListPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsTokenPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsTokenResult(BaseModel):
    token: str
    livekit_url: str


class CallsTurnCredentialsPayload(BaseModel):
    pass


class CallsLinksListPayload(BaseModel):
    start_at: datetime
    end_at: datetime
    channel_id: str | None = Field(default=None)
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CallsLinksUpdatePayload(BaseModel):
    link_token: str = Field(min_length=1)
    body: CallLinkPatch


class CallsLinksRemovePayload(BaseModel):
    link_token: str = Field(min_length=1)


class CallsJoinInfoPayload(BaseModel):
    link_token: str = Field(min_length=1)


class CallsJoinAcceptPayload(BaseModel):
    link_token: str = Field(min_length=1)
    body: GuestJoinRequest | None = Field(default=None)


def _livekit_client(settings: BaseSettings) -> LiveKitClient:
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )


def _livekit_public_url(settings: BaseSettings) -> str:
    host = resolve_context_host()
    if host is not None:
        try:
            return resolve_livekit_public_url(host)
        except ValueError:
            pass
    configured = settings.calls.livekit_public_url or settings.calls.livekit_url
    if str(configured).strip() == "":
        raise ValueError("calls.livekit_public_url or calls.livekit_url must be configured")
    return str(configured).strip()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ttl_hours_from_schedule(scheduled_end: datetime, now: datetime) -> int:
    delta = _as_utc(scheduled_end) - _as_utc(now)
    hours = int(delta.total_seconds() / 3600.0) + 2
    return max(1, min(168, hours))


async def _participant_names_for_call(
    di: Di, call: SyncCall
) -> dict[str, str]:
    out: dict[str, str] = {}
    member_ids = await di.channel_access_service.list_member_user_ids(
        call.channel_id
    )
    for uid in member_ids:
        u = await User.get(uid)
        out[uid] = u.name if u is not None else uid

    for participant_row in await SyncCallParticipant.list_for_call(call.call_id):
        uid = participant_row.user_id
        if uid in out:
            continue
        if uid.startswith("guest:"):
            parts = uid.split(":", 2)
            out[uid] = parts[2] if len(parts) >= 3 else "Гость"
        else:
            u = await User.get(uid)
            out[uid] = u.name if u is not None else uid
    return out


async def _mint_join_short_url(
    di: Di, link_token: str, expires_at: datetime, company_id: str
) -> str:
    return await di.short_link_service.mint_sync_call_join(
        link_token, expires_at, company_id
    )


async def _reconcile_calendar_meeting_channel_members(
    *,
    di: Di,
    channel_id: str,
    company_id: str,
    link_creator_user_id: str,
    calendar_member_user_ids: list[str],
) -> None:
    access = di.channel_access_service
    desired_guests = {
        uid for uid in calendar_member_user_ids if uid and uid != link_creator_user_id
    }
    for uid in sorted(desired_guests):
        await SyncChannelMember.ensure_channel_member_row(
            channel_id, uid, company_id=company_id
        )
        await access.set_member(channel_id, user_id=uid, relation="member")
    current = await access.list_member_user_ids(channel_id)
    desired = {link_creator_user_id} | desired_guests
    for uid in current:
        if uid not in desired:
            _ = await SyncChannelMember.delete_channel_member(
                channel_id, uid, company_id=company_id
            )
            await access.remove_member(channel_id, user_id=uid)


async def op_calls_get(
    payload: CallsGetPayload,
    *,
    user: User,
    di: Di,
) -> CallRead:
    _ = user
    _ = di
    company_id = require_company().company_id
    try:
        call = await SyncCall.require_company_call(payload.call_id, company_id)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc), error_code='not_found') from exc
    participants = await SyncCallParticipant.list_for_call(payload.call_id)
    return call_read_from_entities(call, participants)


async def op_calls_recordings_list(
    payload: CallsRecordingsListPayload,
    *,
    user: User,
    di: Di,
) -> ListResponse[CallRecordingRead]:
    company_id = require_company().company_id
    call = await SyncCall.require_company_call(payload.call_id, company_id)
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the call.", error_code='forbidden')
    rows = await SyncCallRecording.list_for_call(payload.call_id, company_id)
    return ListResponse[CallRecordingRead](
        items=[CallRecordingRead.model_validate(row.model_dump()) for row in rows]
    )


async def op_calls_token(
    payload: CallsTokenPayload,
    *,
    user: User,
    di: Di,
) -> CallsTokenResult:
    company_id = require_company().company_id
    settings = get_settings()
    try:
        call = await SyncCall.require_company_call(payload.call_id, company_id)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc), error_code='not_found') from exc
    if call.mode != "sfu":
        raise WsCommandError(
            "forbidden", f"Call {payload.call_id} is not an SFU call.",
                  error_code='forbidden',
              )
    if not call.livekit_room_name:
        raise WsCommandError(
            "forbidden", f"Call {payload.call_id} has no LiveKit room.",
                  error_code='forbidden',
              )
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(call.channel_id), user_id=user.user_id
    ):
        raise WsCommandError(
            "forbidden", f"No access to call channel {payload.call_id}.",
                  error_code='forbidden',
              )
    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name, identity=user.user_id
    )
    return CallsTokenResult(token=token, livekit_url=_livekit_public_url(settings))


async def op_calls_turn_credentials(
    payload: CallsTurnCredentialsPayload,
    *,
    user: User,
    di: Di,
) -> TurnCredentials:
    _ = payload
    _ = di
    settings = get_settings()
    return generate_turn_credentials(
        user_id=user.user_id,
        turn_host=settings.calls.turn_host,
        turn_port=settings.calls.turn_port,
        turn_secret=settings.calls.turn_secret,
        ttl=settings.calls.turn_credential_ttl,
    )


async def op_calls_links_list(
    payload: CallsLinksListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CallScheduledLinkRead]:
    company_id = require_company().company_id
    rows = await SyncCallLink.list_scheduled_calendar_links_for_user(
        company_id,
        user.user_id,
        range_start=payload.start_at,
        range_end=payload.end_at,
        channel_id=payload.channel_id,
    )
    out: list[CallScheduledLinkRead] = []
    for row in rows:
        if row.scheduled_start_at is None or row.scheduled_end_at is None:
            continue
        if row.calendar_event_id is None:
            continue
        join_url = await _mint_join_short_url(
            di, row.link_token, row.expires_at, row.company_id
        )
        out.append(
            CallScheduledLinkRead(
                link_token=row.link_token,
                channel_id=row.channel_id,
                title=row.title,
                scheduled_start_at=row.scheduled_start_at,
                scheduled_end_at=row.scheduled_end_at,
                calendar_event_id=row.calendar_event_id,
                join_url=join_url,
                expires_at=row.expires_at,
            )
        )
    page = out[payload.offset : payload.offset + payload.limit]
    return OffsetPage[CallScheduledLinkRead](
        items=page, total=len(out), limit=payload.limit, offset=payload.offset
    )


async def op_calls_links_create(
    body: CallLinkCreate,
    *,
    user: User,
    di: Di,
) -> CallLinkRead:
    company_id = require_company().company_id
    actor_id = user.user_id

    channel_id: str
    attached_call_id: str | None = None
    calendar_title: str | None = None
    cal_start: datetime | None = None
    cal_end: datetime | None = None
    cal_event_id: str | None = None
    ttl_hours = body.ttl_hours
    is_persistent_channel_link = False

    if body.calendar_event_id:
        scheduled_title = body.scheduled_title
        scheduled_start_at = body.scheduled_start_at
        scheduled_end_at = body.scheduled_end_at
        calendar_member_user_ids = body.calendar_member_user_ids
        if (
            scheduled_title is None
            or scheduled_start_at is None
            or scheduled_end_at is None
            or calendar_member_user_ids is None
        ):
            message = (
                "calendar_event_id требует scheduled_title, scheduled_start_at, "
                "scheduled_end_at и calendar_member_user_ids."
            )
            raise WsCommandError(
                "ws_invalid_payload",
                message,
                      error_code='ws_invalid_payload',
                  )
        dup = await SyncCallLink.find_by_calendar_event(
            company_id, body.calendar_event_id
        )
        if dup is not None:
            raise WsCommandError(
                "conflict", "A link already exists for this calendar event.",
                      error_code='conflict',
                  )
        channel_id = uuid4().hex
        ch = SyncChannel(
            channel_id=channel_id,
            company_id=company_id,
            namespace="default",
            type=CHANNEL_TYPE_CALENDAR_MEETING,
            name=scheduled_title.strip(),
            is_private=False,
            created_at=datetime.now(UTC),
            created_by_user_id=actor_id,
            pinned_message_ids=[],
        )
        _ = await SyncChannel.set(ch)
        member_ids = [uid for uid in calendar_member_user_ids if uid and uid != actor_id]
        await SyncChannelMember.ensure_channel_member_row(
            channel_id, actor_id, company_id=company_id
        )
        for uid in member_ids:
            await SyncChannelMember.ensure_channel_member_row(
                channel_id, uid, company_id=company_id
            )
        try:
            await di.channel_access_service.sync_channel_created(
                channel_id,
                company_id=company_id,
                owner_user_id=actor_id,
                member_user_ids=member_ids,
            )
        except Exception:
            _ = await SyncChannel.delete_by_id(channel_id)
            raise
        now = datetime.now(UTC)
        ttl_hours = _ttl_hours_from_schedule(scheduled_end_at, now)
        expires_at = now + timedelta(hours=ttl_hours)
        calendar_title = scheduled_title.strip()
        cal_start = scheduled_start_at
        cal_end = scheduled_end_at
        cal_event_id = body.calendar_event_id
    else:
        if body.channel_id is None:
            raise WsCommandError(
                "ws_invalid_payload",
                "channel_id is required for a link without calendar_event_id.",
                      error_code='ws_invalid_payload',
                  )
        channel_id = body.channel_id
        if not await di.authz_service.can_view(
            AuthzObject.sync_channel(channel_id), user_id=actor_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)
        if body.call_id:
            existing = await SyncCall.require_company_call(body.call_id, company_id)
            if existing.channel_id != channel_id:
                raise WsCommandError(
                    "ws_invalid_payload", "Call belongs to another channel.",
                          error_code='ws_invalid_payload',
                      )
            if existing.status not in ("ringing", "active"):
                raise WsCommandError(
                    "forbidden",
                    "Conference link is available only for an active or incoming call.",
                          error_code='forbidden',
                      )
            if existing.mode != "sfu":
                raise WsCommandError(
                    "forbidden", "Guest link is supported only for SFU calls.",
                          error_code='forbidden',
                      )
            if not existing.livekit_room_name:
                raise WsCommandError("forbidden", "Call has no LiveKit room.", error_code='forbidden')
            attached_call_id = existing.call_id
        else:
            ch = await SyncChannel.get(channel_id)
            if ch is None:
                raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
            if ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
                raise WsCommandError(
                    "ws_invalid_payload",
                    "A persistent link for a calendar meeting channel is not created via channel_id.",
                          error_code='ws_invalid_payload',
                      )
            existing_p = await SyncCallLink.find_persistent_for_channel(
                company_id, channel_id
            )
            if body.reuse_channel_link:
                if existing_p is not None:
                    await SyncCallLink.set_expires_at(existing_p.link_token, expires_at)
                    join_url = await _mint_join_short_url(
                        di, existing_p.link_token, expires_at, company_id
                    )
                    return CallLinkRead(
                        link_token=existing_p.link_token,
                        channel_id=channel_id,
                        call_type="video",
                        expires_at=expires_at,
                        join_url=join_url,
                        title=existing_p.title,
                        scheduled_start_at=existing_p.scheduled_start_at,
                        scheduled_end_at=existing_p.scheduled_end_at,
                        calendar_event_id=existing_p.calendar_event_id,
                    )
            else:
                if existing_p is not None:
                    _ = await PlatformShortLink.delete_sync_by_link_token(existing_p.link_token)
                    deleted = await SyncCallLink.delete_in_company(
                        company_id, existing_p.link_token
                    )
                    if not deleted:
                        raise WsCommandError("internal", "Failed to replace the persistent link.", error_code='internal')
            is_persistent_channel_link = True

    link_token = uuid4().hex
    link = SyncCallLink(
        link_token=link_token,
        channel_id=channel_id,
        company_id=company_id,
        call_id=attached_call_id,
        call_type="video",
        created_by_user_id=actor_id,
        expires_at=expires_at,
        title=calendar_title,
        scheduled_start_at=cal_start,
        scheduled_end_at=cal_end,
        calendar_event_id=cal_event_id,
        is_persistent_channel_link=is_persistent_channel_link,
    )
    _ = await SyncCallLink.set(link)

    join_url = await _mint_join_short_url(di, link_token, expires_at, company_id)
    return CallLinkRead(
        link_token=link_token,
        channel_id=channel_id,
        call_type="video",
        expires_at=expires_at,
        join_url=join_url,
        title=calendar_title,
        scheduled_start_at=cal_start,
        scheduled_end_at=cal_end,
        calendar_event_id=cal_event_id,
    )


async def op_calls_links_update(
    payload: CallsLinksUpdatePayload,
    *,
    user: User,
    di: Di,
) -> CallLinkRead:
    company_id = require_company().company_id
    body = payload.body
    link = await SyncCallLink.require_company_call_link(
        payload.link_token, company_id
    )
    if link.calendar_event_id is None:
        raise WsCommandError(
            "forbidden", "Patch is supported only for calendar links.",
                  error_code='forbidden',
              )
    if not await di.authz_service.can_view(
        AuthzObject.sync_channel(link.channel_id), user_id=user.user_id
    ):
        raise WsCommandError("forbidden", "No access to the link.", error_code='forbidden')

    raw_start = body.scheduled_start_at if body.scheduled_start_at is not None else link.scheduled_start_at
    raw_end = body.scheduled_end_at if body.scheduled_end_at is not None else link.scheduled_end_at
    if raw_start is None or raw_end is None:
        raise WsCommandError("ws_invalid_payload", "Link must have schedule bounds.", error_code='ws_invalid_payload')
    new_start = _as_utc(raw_start)
    new_end = _as_utc(raw_end)
    if new_start >= new_end:
        raise WsCommandError("ws_invalid_payload", "Invalid meeting interval.", error_code='ws_invalid_payload')

    new_title = body.scheduled_title if body.scheduled_title is not None else link.title
    now = datetime.now(UTC)
    new_expires = now + timedelta(hours=_ttl_hours_from_schedule(new_end, now))

    await SyncCallLink.update_calendar_call_link(
        payload.link_token,
        company_id,
        title=new_title,
        scheduled_start_at=new_start,
        scheduled_end_at=new_end,
        expires_at=new_expires,
    )
    if body.scheduled_title is not None:
        ch = await SyncChannel.get(link.channel_id)
        if ch is None or ch.company_id != company_id:
            raise WsCommandError("not_found", "Link channel not found.", error_code='not_found')
        name = body.scheduled_title.strip()
        if name == "":
            raise WsCommandError("ws_invalid_payload", "scheduled_title must not be empty.", error_code='ws_invalid_payload')
        _ = await SyncChannel.rename_channel(ch, name)
    if body.calendar_member_user_ids is not None:
        await _reconcile_calendar_meeting_channel_members(
            di=di,
            channel_id=link.channel_id,
            company_id=company_id,
            link_creator_user_id=link.created_by_user_id,
            calendar_member_user_ids=body.calendar_member_user_ids,
        )
    updated = await SyncCallLink.require_company_call_link(
        payload.link_token, company_id
    )
    join_url = await _mint_join_short_url(
        di, payload.link_token, updated.expires_at, company_id
    )
    return CallLinkRead(
        link_token=updated.link_token,
        channel_id=updated.channel_id,
        call_type="video",
        expires_at=updated.expires_at,
        join_url=join_url,
        title=updated.title,
        scheduled_start_at=updated.scheduled_start_at,
        scheduled_end_at=updated.scheduled_end_at,
        calendar_event_id=updated.calendar_event_id,
    )


async def op_calls_links_remove(
    payload: CallsLinksRemovePayload,
    *,
    user: User,
    di: Di,
) -> None:
    company_id = require_company().company_id
    link = await SyncCallLink.require_company_call_link(
        payload.link_token, company_id
    )
    if link.calendar_event_id is None:
        raise WsCommandError(
            "forbidden", "Delete via this contract is only for calendar links.",
                  error_code='forbidden',
              )
    can_admin = await di.authz_service.can_admin(
        AuthzObject.sync_channel(link.channel_id), user_id=user.user_id
    )
    if link.created_by_user_id != user.user_id and not can_admin:
        raise WsCommandError("forbidden", "No permission to delete this link.", error_code='forbidden')
    channel_id = link.channel_id
    deleted = await SyncCallLink.delete_in_company(
        company_id, payload.link_token
    )
    if not deleted:
        raise WsCommandError("not_found", "Link not found.", error_code='not_found')
    _ = await PlatformShortLink.delete_sync_by_link_token(payload.link_token)
    ch = await SyncChannel.get(channel_id)
    if ch is not None and ch.company_id == company_id and ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
        await di.channel_access_service.sync_channel_deleted(channel_id)
        _ = await SyncChannel.delete_by_id(channel_id)
    return None


async def op_calls_join_info(
    payload: CallsJoinInfoPayload,
    *,
    user: User,
    di: Di,
) -> CallLinkInfo:
    _ = user
    _ = di
    try:
        link = await SyncCallLink.require_active_call_link(payload.link_token)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc), error_code='not_found') from exc

    channel = await SyncChannel.get(link.channel_id)
    channel_name = channel.name if channel else None

    creator_name = link.created_by_user_id
    creator_avatar_url: str | None = None
    creator = await User.get(link.created_by_user_id)
    if creator is not None:
        creator_name = creator.name
        creator_avatar_url = creator.avatar_url

    return CallLinkInfo(
        link_token=payload.link_token,
        company_id=link.company_id,
        channel_id=link.channel_id,
        channel_name=channel_name,
        creator_display_name=creator_name,
        creator_avatar_url=creator_avatar_url,
        call_type="video",
        expires_at=link.expires_at,
    )


async def op_calls_join_accept(
    payload: CallsJoinAcceptPayload,
    *,
    user: User,
    di: Di,
) -> JoinResponse:
    settings = get_settings()
    try:
        link = await SyncCallLink.require_active_call_link(payload.link_token)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc), error_code='not_found') from exc

    is_authenticated = user.user_id not in ("anonymous", "")

    participant_identity: str
    if is_authenticated:
        participant_identity = user.user_id
    else:
        if payload.body is None or not payload.body.guest_name.strip():
            raise WsCommandError(
                "ws_invalid_payload",
                "guest_name is required for guest join.",
                      error_code='ws_invalid_payload',
                  )
        safe_name = payload.body.guest_name.strip().replace(":", "_")
        participant_identity = f"guest:{uuid4().hex[:8]}:{safe_name}"

    if link.call_id:
        call = await SyncCall.require_company_call(link.call_id, link.company_id)
        if call.status == "ended":
            livekit_room = call.livekit_room_name
            if not livekit_room:
                raise WsCommandError(
                    "internal",
                    "Ended call has no LiveKit room.",
                          error_code='internal',
                      )
            await _livekit_client(settings).create_room(
                livekit_room,
                company_id=link.company_id,
                user_id=participant_identity,
            )
            new_call = SyncCall(
                call_id=uuid4().hex,
                company_id=link.company_id,
                channel_id=link.channel_id,
                mode="sfu",
                call_type="video",
                status="active",
                livekit_room_name=livekit_room,
                started_at=datetime.now(UTC),
                created_by_user_id=link.created_by_user_id,
            )
            _ = await SyncCall.set(new_call)
            await SyncCallLink.attach_call(payload.link_token, new_call.call_id)
            call = new_call
    else:
        livekit_room_name = f"link-{payload.link_token[:16]}"
        await _livekit_client(settings).create_room(
            livekit_room_name,
            company_id=link.company_id,
            user_id=participant_identity,
        )
        call = SyncCall(
            call_id=uuid4().hex,
            company_id=link.company_id,
            channel_id=link.channel_id,
            mode="sfu",
            call_type="video",
            status="active",
            livekit_room_name=livekit_room_name,
            started_at=datetime.now(UTC),
            created_by_user_id=link.created_by_user_id,
        )
        _ = await SyncCall.set(call)
        await SyncCallLink.attach_call(payload.link_token, call.call_id)

    if not call.livekit_room_name:
        raise WsCommandError("internal", "Call has no LiveKit room.", error_code='internal')

    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name, identity=participant_identity
    )
    participant_names = await _participant_names_for_call(di, call)

    return JoinResponse(
        call_id=call.call_id,
        call_type="video",
        livekit_token=token,
        livekit_url=_livekit_public_url(settings),
        participant_identity=participant_identity,
        meeting_admin_user_id=call.created_by_user_id,
        mode="sfu",
        participant_names=participant_names,
    )


# ===========================================================================
# Участники компании + общие каналы
# ===========================================================================


class CompanyMembersListPayload(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CompanySharedChannelsListPayload(BaseModel):
    peer_user_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


async def op_company_members_list(
    payload: CompanyMembersListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[CompanyMemberRead]:
    _ = di
    company_id = require_company().company_id
    company = await Company.get(company_id)
    if company is None:
        raise WsCommandError("not_found", "Company not found.", error_code='not_found')

    all_member_uids = [uid for uid in company.members if uid != user.user_id]
    total = len(all_member_uids)
    member_uids = all_member_uids[payload.offset : payload.offset + payload.limit]

    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise WsCommandError("internal", "database.redis_url is not set.", error_code='internal')

    presence_map, users_by_id = await asyncio.gather(
        batch_peer_presence(redis_url, member_uids),
        User.get_many(member_uids),
    )

    items: list[CompanyMemberRead] = []
    for uid in member_uids:
        roles_raw = company.members[uid]
        member_user = users_by_id.get(uid)
        if member_user is None:
            raise WsCommandError(
                "internal",
                f"Member {uid} is listed in the company, but the user was not found.",
                      error_code='internal',
                  )
        roles = list(roles_raw)
        pr = presence_map[uid]
        items.append(
            CompanyMemberRead(
                user_id=uid,
                name=member_user.name,
                roles=roles,
                avatar_url=member_user.avatar_url,
                is_online=pr.is_online,
                last_seen_at=pr.last_seen_at,
            )
        )
    items.sort(key=lambda m: m.name.casefold())
    return OffsetPage[CompanyMemberRead](
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_company_shared_channels_list(
    payload: CompanySharedChannelsListPayload,
    *,
    user: User,
    di: Di,
) -> OffsetPage[ChannelRead]:
    company_id = require_company().company_id
    company = await Company.get(company_id)
    if company is None:
        raise WsCommandError("not_found", "Company not found.", error_code='not_found')
    if payload.peer_user_id not in company.members:
        raise WsCommandError("not_found", "User is not in the company.", error_code='not_found')

    if payload.peer_user_id == user.user_id:
        candidates = await SyncChannel.list_channels_for_user(
            user.user_id,
            namespace=None,
            limit=payload.limit,
            offset=payload.offset,
            company_id=company_id,
        )
        channels = await _filter_channels_by_can_view(
            di, candidates, user_id=user.user_id
        )
    else:
        candidates = await SyncChannel.list_channels_where_both_members(
            user.user_id,
            payload.peer_user_id,
            limit=payload.limit,
            offset=payload.offset,
            company_id=company_id,
        )
        channels = await _filter_channels_by_can_view(
            di,
            candidates,
            user_id=user.user_id,
            peer_user_id=payload.peer_user_id,
        )

    channel_ids = [c.channel_id for c in channels]
    summaries = await SyncMessage.channel_lane_summaries(
        company_id=company_id,
        channel_ids=channel_ids,
        viewer_user_id=user.user_id,
    )
    items: list[ChannelRead] = []
    for c in channels:
        items.append(
            await channel_read_from_entity(
                c,
                viewer_user_id=user.user_id,
                channel_access=di.channel_access_service,
                resolve_user=True,
                company_id=company_id,
                lane_summary=summaries[c.channel_id],
            )
        )
    return OffsetPage[ChannelRead](
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


# ===========================================================================
# Файлы (метаданные после REST upload)
# ===========================================================================


class FilesUploadCompletedPayload(BaseModel):
    file_id: str = Field(min_length=1)


async def op_files_upload_completed(
    payload: FilesUploadCompletedPayload,
    *,
    user: User,
    di: Di,
) -> FileRef:
    """Подтверждение метаданных файла после chunked REST upload.

    Бинарный поток идёт через `POST /sync/api/v1/files/uploads*` (chunked),
    а через WS клиент шлёт этот фрейм с `file_id` и получает `FileRef`.
    """
    _ = user
    _ = di
    record: FileRecord | None = await FileRecord.get(payload.file_id)
    if record is None:
        raise WsCommandError("not_found", f"File {payload.file_id!r} not found.", error_code='not_found')
    return stored_file_ref(record)
