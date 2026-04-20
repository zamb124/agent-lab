"""Единый реестр операций Sync — один handler, два транспорта.

Контракт:
    async def op_<entity>_<verb>(
        payload: <Op>Payload,
        *,
        user: User,
        container: SyncContainer,
    ) -> <Op>Result | None

Для каждой операции:
  - REST-route в `apps/sync/api/**` валидирует входное тело через Pydantic
    (FastAPI), вызывает `op_*` напрямую и сериализует результат.
  - WS command-handler (`apps/sync/realtime/command_router.py::_make_ws_handler`)
    валидирует payload через тот же Pydantic-класс и вызывает ту же `op_*`.

Zero-fallback canon (см. `main.mdc`):
  - Никаких `or default` / `getattr(payload, k, default)` — поля валидирует
    Pydantic, отсутствие = `ValidationError` → `WsCommandError("ws_invalid_payload", ...)`.
  - Никаких `try/except Exception` вокруг repository-вызовов. IO-ошибки
    идут наверх как 500.
  - Бизнес-инварианты: явный `raise WsCommandError(code, detail)`.
    Не «вернуть пустой результат».
  - `resolve_company_id` бросает, если контекста нет, — никаких неявных
    дефолтов на `system` или `user.active_company_id or "default"`.

Mutating-операции исполняются in-process. TaskIQ — только для явно
помеченных heavy-операций (`messages.transcribe_audio/video/call`),
запускаемых через `.kiq(...)` внутри `op_*` после валидации/обновления
статуса.
"""

from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Awaitable, Callable, Generic, Literal, Optional, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from apps.sync.channel_read_helpers import channel_read_from_entity
from apps.sync.constants import CHANNEL_TYPE_CALENDAR_MEETING
from apps.sync.container import SyncContainer
from apps.sync.db.models import SyncCall, SyncCallLink, SyncCallParticipant, SyncChannel
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.calls import (
    CallLinkCreate,
    CallLinkInfo,
    CallLinkPatch,
    CallLinkRead,
    CallParticipantRead,
    CallRead,
    CallScheduledLinkRead,
    GuestJoinRequest,
    JoinResponse,
)
from apps.sync.models.channels import (
    ChannelCreate,
    ChannelMemberAdd,
    ChannelMemberRead,
    ChannelNotificationSettingsUpdate,
    ChannelRead,
    ChannelUpdate,
)
from apps.sync.models.common import UserBrief
from apps.sync.models.company_members import CompanyMemberRead
from apps.sync.models.git import GitResourceRefCreate, GitResourceRefRead
from apps.sync.models.messages import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageEdit,
    MessageRead,
    MessageStatus,
    TextPlainContent,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.threads import ThreadCreate, ThreadRead, ThreadRow
from apps.sync.realtime.call_handlers import (
    _call_read_from_entities,
    handle_call_accept,
    handle_call_decline,
    handle_call_hangup,
    handle_call_invite,
)
from apps.sync.realtime.events import (
    MessageStatusChangedPayload,
    RealtimeEvent,
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
from apps.sync.realtime.handlers import (
    _build_livekit_recording_client,
    _channel_read_entity,
    _channel_recipient_user_ids,
    _create_channel,
    _create_thread,
    _enqueue_channel_message_notifications,
    _ensure_actor_may_send_to_channel,
    _find_first_audio_content_index,
    _maybe_start_speech_to_chat_poll,
    _message_read_from_db,
    _normalize_message_create_mentions,
    _normalize_s3_egress_endpoint,
    _send_message,
    _set_audio_transcription_state,
    _set_video_transcription_state,
    _stop_and_finalize_recording,
    _update_channel,
    _upsert_git_resource,
)
from apps.sync.realtime.publish_events import publish_realtime_events
from apps.sync.ws_presence import batch_peer_presence
from core.calls.livekit_client import LiveKitClient
from core.calls.models import SignalType, TurnCredentials
from core.calls.turn import generate_turn_credentials
from core.config import get_settings
from core.context import get_context
from core.files.models import FileRecord
from core.models.identity_models import User
from core.pagination import ListResponse, OffsetPage
from core.websocket import WsCommandError

PayloadT = TypeVar("PayloadT", bound=BaseModel)
ResultT = TypeVar("ResultT", bound=BaseModel)


OperationFn = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class Operation(Generic[PayloadT, ResultT]):
    """Описание операции: payload-модель + бизнес-функция.

    `fn` обязана иметь сигнатуру:
        async def fn(payload: PayloadT, *, user: User, container: SyncContainer)
            -> ResultT | None
    """

    canonical_type: str
    payload_model: type[PayloadT]
    fn: OperationFn
    result_model: type[ResultT] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_type, str) or not self.canonical_type:
            raise ValueError("Operation.canonical_type must be non-empty string")
        if not self.canonical_type.endswith("_requested"):
            raise ValueError(
                f"Operation.canonical_type {self.canonical_type!r} must end with '_requested'"
            )
        if not isinstance(self.payload_model, type) or not issubclass(self.payload_model, BaseModel):
            raise ValueError(
                f"Operation.payload_model for {self.canonical_type!r} must be a Pydantic BaseModel subclass"
            )
        if not callable(self.fn):
            raise ValueError(f"Operation.fn for {self.canonical_type!r} must be callable")


def resolve_company_id(user: User) -> str:
    """Достать company_id для команды.

    Никаких неявных дефолтов: если контекста нет — `WsCommandError`.
    """
    context = get_context()
    if context is not None and context.active_company is not None:
        return context.active_company.company_id
    if isinstance(user.active_company_id, str) and user.active_company_id:
        return user.active_company_id
    raise WsCommandError("ws_no_company", "Нет active_company_id для команды Sync.")


def parse_payload(model: type[PayloadT], raw: Any) -> PayloadT:
    """Валидация входа через Pydantic. ValidationError → WsCommandError."""
    try:
        return model.model_validate(raw if raw is not None else {})
    except ValidationError as exc:
        raise WsCommandError("ws_invalid_payload", str(exc)) from exc


def dump_result(result: Any) -> dict[str, Any] | None:
    """Привести результат операции к JSON-словарю или None."""
    if result is None:
        return None
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return result
    raise WsCommandError(
        "ws_invalid_result",
        f"Operation result must be Pydantic model | dict | None, got {type(result).__name__}",
    )


# Маппинг кодов `WsCommandError` в HTTP-статусы для REST-зеркал.
_HTTP_STATUS_BY_CODE: dict[str, int] = {
    "ws_invalid_payload": 400,
    "ws_invalid_cursor": 400,
    "ws_invalid_result": 500,
    "ws_no_company": 400,
    "not_found": 404,
    "forbidden": 403,
    "conflict": 409,
    "internal": 500,
}


def ws_command_error_status(error: WsCommandError) -> int:
    """HTTP-статус для `WsCommandError`. Неизвестный код = 500."""
    return _HTTP_STATUS_BY_CODE.get(error.code, 500)


# ---------------------------------------------------------------------------
# Cursor encoding (общий формат для messages list cursor через WS и REST)
# ---------------------------------------------------------------------------


def _encode_message_cursor(*, sent_at: datetime, message_id: str) -> str:
    payload = {"sent_at": sent_at.isoformat(), "message_id": message_id}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")
    return encoded.rstrip("=")


def _decode_message_cursor(cursor: str) -> tuple[datetime, str]:
    padded = cursor + ("=" * ((4 - len(cursor) % 4) % 4))
    try:
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise WsCommandError("ws_invalid_cursor", "cursor must be base64url(JSON)") from exc
    if not isinstance(payload, dict):
        raise WsCommandError("ws_invalid_cursor", "cursor payload must be object")
    sent_at_raw = payload.get("sent_at")
    message_id = payload.get("message_id")
    if not isinstance(sent_at_raw, str) or not sent_at_raw:
        raise WsCommandError("ws_invalid_cursor", "cursor.sent_at required")
    if not isinstance(message_id, str) or not message_id:
        raise WsCommandError("ws_invalid_cursor", "cursor.message_id required")
    try:
        sent_at = datetime.fromisoformat(sent_at_raw)
    except ValueError as exc:
        raise WsCommandError("ws_invalid_cursor", "cursor.sent_at must be ISO datetime") from exc
    return sent_at, message_id


# ===========================================================================
# Channels
# ===========================================================================


class ChannelsListPayload(BaseModel):
    namespace: str | None = Field(default=None)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ChannelsListResult(BaseModel):
    items: list[ChannelRead]
    total: int
    limit: int
    offset: int


class ChannelsCreatePayload(BaseModel):
    body: ChannelCreate


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
    role: str = Field(default="member", min_length=1)


class ChannelsListMembersPayload(BaseModel):
    channel_id: str = Field(min_length=1)


class ChannelsListMembersResult(BaseModel):
    items: list[ChannelMemberRead]


async def _build_channel_read(
    container: SyncContainer,
    channel: SyncChannel,
    *,
    viewer_id: str,
    company_id: str,
) -> ChannelRead:
    summaries = await container.message_repository.channel_lane_summaries_batch(
        company_id=company_id,
        channel_ids=[channel.channel_id],
        viewer_user_id=viewer_id,
    )
    return await channel_read_from_entity(
        channel,
        viewer_user_id=viewer_id,
        channel_repository=container.channel_repository,
        user_repository=container.user_repository,
        company_id=company_id,
        lane_summary=summaries[channel.channel_id],
    )


async def op_channels_list(
    payload: ChannelsListPayload,
    *,
    user: User,
    container: SyncContainer,
) -> ChannelsListResult:
    company_id = resolve_company_id(user)
    channels = await container.channel_repository.list_for_user(
        user.user_id,
        namespace=payload.namespace,
        limit=payload.limit,
        offset=payload.offset,
        company_id=company_id,
    )
    channel_ids = [c.channel_id for c in channels]
    summaries = await container.message_repository.channel_lane_summaries_batch(
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
                channel_repository=container.channel_repository,
                user_repository=container.user_repository,
                company_id=company_id,
                lane_summary=summaries[c.channel_id],
            )
        )
    return ChannelsListResult(
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


async def op_channels_create(
    payload: ChannelsCreatePayload,
    *,
    user: User,
    container: SyncContainer,
) -> ChannelRead:
    company_id = resolve_company_id(user)
    channel = await _create_channel(
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
        channels=container.channel_repository,
        namespaces=container.namespace_repository,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, channel.id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> ChannelRead:
    company_id = resolve_company_id(user)
    return await _update_channel(
        payload.channel_id,
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
        channels=container.channel_repository,
    )


async def op_channels_mark_read(
    payload: ChannelsMarkReadPayload,
    *,
    user: User,
    container: SyncContainer,
) -> None:
    company_id = resolve_company_id(user)
    role = await container.channel_repository.get_member_role(payload.channel_id, user.user_id)
    if role is None:
        raise WsCommandError(
            "forbidden", f"Пользователь не состоит в канале {payload.channel_id}."
        )
    max_at = await container.message_repository.max_root_lane_sent_at(
        payload.channel_id, company_id=company_id
    )
    read_at = max_at if max_at is not None else datetime.now(UTC)
    await container.channel_repository.set_member_last_read_at(
        payload.channel_id, user.user_id, read_at, company_id=company_id
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> None:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError(
            "forbidden", f"Пользователь не состоит в канале {payload.channel_id}."
        )
    if payload.thread_id is not None and payload.thread_id != "":
        thread = await container.thread_repository.get(payload.thread_id)
        if thread is None:
            raise WsCommandError("not_found", f"Тред {payload.thread_id} не найден.")
        if thread.company_id != company_id:
            raise WsCommandError("forbidden", "Тред не принадлежит компании.")
        if thread.channel_id != payload.channel_id:
            raise WsCommandError("forbidden", "Тред не принадлежит указанному каналу.")
    user_obj = await container.user_repository.get(user.user_id)
    if user_obj is None:
        raise WsCommandError("not_found", f"Пользователь {user.user_id} не найден.")
    user_brief = UserBrief(
        user_id=user.user_id, display_name=user_obj.name, avatar_url=user_obj.avatar_url
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> ChannelRead:
    company_id = resolve_company_id(user)
    ch = await container.channel_repository.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Канал не найден.")
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    await container.channel_repository.set_member_notifications_muted(
        payload.channel_id,
        user.user_id,
        payload.notifications_muted,
        company_id=company_id,
    )
    return await _build_channel_read(
        container, ch, viewer_id=user.user_id, company_id=company_id
    )


async def op_channels_add_member(
    payload: ChannelsAddMemberPayload,
    *,
    user: User,
    container: SyncContainer,
) -> ChannelMemberRead:
    company_id = resolve_company_id(user)
    ch = await container.channel_repository.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Канал не найден.")
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    await container.channel_repository.upsert_member(
        payload.channel_id,
        payload.user_id,
        payload.role,
        company_id=company_id,
    )
    recipients = await container.channel_repository.list_member_user_ids(
        payload.channel_id, company_id=company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> ChannelsListMembersResult:
    company_id = resolve_company_id(user)
    ch = await container.channel_repository.get(payload.channel_id)
    if ch is None or ch.company_id != company_id:
        raise WsCommandError("not_found", "Канал не найден.")
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    rows = await container.channel_repository.list_member_rows(
        payload.channel_id, company_id=company_id
    )
    return ChannelsListMembersResult(
        items=[ChannelMemberRead(user_id=uid, role=role) for uid, role in rows]
    )


# ===========================================================================
# Threads
# ===========================================================================


class ThreadsListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class ThreadsListResult(BaseModel):
    items: list[ThreadRow]
    total: int
    limit: int
    offset: int


class ThreadsItemPayload(BaseModel):
    thread_id: str = Field(min_length=1)


class ThreadsCreatePayload(BaseModel):
    body: ThreadCreate


async def op_threads_list(
    payload: ThreadsListPayload,
    *,
    user: User,
    container: SyncContainer,
) -> ThreadsListResult:
    company_id = resolve_company_id(user)
    threads = await container.thread_repository.list_by_channel(
        payload.channel_id,
        limit=payload.limit,
        company_id=company_id,
    )
    items = [
        ThreadRow(
            id=t.thread_id,
            channel_id=t.channel_id,
            root_message_id=t.root_message_id,
            title=t.title,
            created_at=t.created_at,
            created_by_user_id=t.created_by_user_id,
        )
        for t in threads
    ]
    return ThreadsListResult(
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


async def op_threads_item(
    payload: ThreadsItemPayload,
    *,
    user: User,
    container: SyncContainer,
) -> ThreadRow:
    _ = resolve_company_id(user)
    thread = await container.thread_repository.get(payload.thread_id)
    if thread is None:
        raise WsCommandError("not_found", f"Thread {payload.thread_id!r} not found.")
    return ThreadRow(
        id=thread.thread_id,
        channel_id=thread.channel_id,
        root_message_id=thread.root_message_id,
        title=thread.title,
        created_at=thread.created_at,
        created_by_user_id=thread.created_by_user_id,
    )


async def op_threads_create(
    payload: ThreadsCreatePayload,
    *,
    user: User,
    container: SyncContainer,
) -> ThreadRead:
    company_id = resolve_company_id(user)
    thread = await _create_thread(
        payload.body,
        actor_user_id=user.user_id,
        company_id=company_id,
        threads=container.thread_repository,
        messages=container.message_repository,
        user_repository=container.user_repository,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, thread.channel_id, company_id
    )
    await publish_realtime_events(
        [
            event_thread_created(
                thread, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return thread


# ===========================================================================
# Messages
# ===========================================================================


class MessagesListPayload(BaseModel):
    channel_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    before: str | None = Field(default=None)
    after: str | None = Field(default=None)


class MessagesListResult(BaseModel):
    items: list[MessageRead]
    next_cursor: str | None
    prev_cursor: str | None


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
    container: SyncContainer,
) -> MessagesListResult:
    company_id = resolve_company_id(user)
    if payload.before is not None and payload.after is not None:
        raise WsCommandError(
            "ws_invalid_payload", "before and after are mutually exclusive"
        )

    before_sent_at: datetime | None = None
    before_message_id: str | None = None
    if payload.before is not None and payload.before != "":
        before_sent_at, before_message_id = _decode_message_cursor(payload.before)
    after_sent_at: datetime | None = None
    after_message_id: str | None = None
    if payload.after is not None and payload.after != "":
        after_sent_at, after_message_id = _decode_message_cursor(payload.after)

    window = await container.message_repository.list_by_channel_cursor(
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
        return MessagesListResult(items=[], next_cursor=None, prev_cursor=None)

    user_ids = list({m.sender_user_id for m in rows})
    users_by_id = await container.user_repository.get_many(user_ids)

    chronological = list(reversed(rows))
    items: list[MessageRead] = []
    for m in chronological:
        content_rows = await container.message_repository.list_contents(m.message_id)
        contents = [
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
            for row in content_rows
        ]
        u = users_by_id.get(m.sender_user_id)
        if u is None:
            sender = UserBrief(
                user_id=m.sender_user_id,
                display_name=m.sender_user_id,
                avatar_url=None,
            )
        else:
            sender = UserBrief(
                user_id=m.sender_user_id, display_name=u.name, avatar_url=u.avatar_url
            )
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
    return MessagesListResult(items=items, next_cursor=next_cursor, prev_cursor=prev_cursor)


async def op_messages_send(
    payload: MessagesSendPayload,
    *,
    user: User,
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    await _ensure_actor_may_send_to_channel(
        channel_id=payload.channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        body=payload.body,
        channels=container.channel_repository,
        calls=container.call_repository,
    )
    normalized_body = await _normalize_message_create_mentions(
        payload.body,
        channel_id=payload.channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        channels=container.channel_repository,
    )
    message = await _send_message(
        payload.channel_id,
        normalized_body,
        actor_user_id=user.user_id,
        company_id=company_id,
        messages=container.message_repository,
        user_repository=container.user_repository,
    )
    notify_payload_dummy = MessagesSendPayload(
        channel_id=payload.channel_id, body=normalized_body
    )
    await _enqueue_channel_message_notifications(
        payload=notify_payload_dummy,
        message=message,
        company_id=company_id,
        actor_user_id=user.user_id,
        channels=container.channel_repository,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    events: list[RealtimeEvent] = [
        event_message_created(
            message, company_id=company_id, recipient_user_ids=recipients
        ),
    ]

    channel_entity = await container.channel_repository.get(payload.channel_id)
    if channel_entity is None:
        raise WsCommandError("not_found", f"Канал {payload.channel_id} не найден.")
    if channel_entity.transcribe_voice_messages:
        audio_idx = _find_first_audio_content_index(normalized_body.contents)
        if audio_idx is not None:
            block = normalized_body.contents[audio_idx]
            if isinstance(block.data, AudioAttachmentContent):
                if (
                    block.data.transcription_status == AudioTranscriptionStatus.IDLE
                    and not block.data.source_speech_to_chat
                ):
                    processing_contents = _set_audio_transcription_state(
                        list(message.contents),
                        status=AudioTranscriptionStatus.PROCESSING,
                        transcription_text=None,
                        transcription_error=None,
                    )
                    edited_at = datetime.now(tz=UTC)
                    await container.message_repository.replace_message_contents(
                        message.id, processing_contents, edited_at
                    )
                    proc_entity = await container.message_repository.get_by_id_for_company(
                        message.id, company_id
                    )
                    if proc_entity is None:
                        raise WsCommandError(
                            "internal", "Сообщение пропало после запуска авто-транскрипции."
                        )
                    message = await _message_read_from_db(
                        proc_entity, container.message_repository, container.user_repository
                    )
                    events.append(
                        event_message_updated(
                            message,
                            company_id=company_id,
                            recipient_user_ids=recipients,
                        ),
                    )
                    from apps.sync.realtime.tasks import sync_transcribe_audio_message_task

                    await sync_transcribe_audio_message_task.kiq(
                        channel_id=payload.channel_id,
                        message_id=message.id,
                        company_id=company_id,
                        actor_user_id=user.user_id,
                    )
    await publish_realtime_events(events)
    return message


async def op_messages_mark_read(
    payload: MessagesMarkReadPayload,
    *,
    user: User,
    container: SyncContainer,
) -> None:
    company_id = resolve_company_id(user)
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    m = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Сообщение удалено.")
    if m.sender_user_id != user.user_id:
        raise WsCommandError("forbidden", "Редактировать может только автор.")
    edited_at = datetime.now(tz=UTC)
    await container.message_repository.replace_message_contents(
        payload.message_id, payload.body.contents, edited_at
    )
    m2 = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise WsCommandError("internal", "Сообщение пропало после редактирования.")
    read = await _message_read_from_db(
        m2, container.message_repository, container.user_repository
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> dict[str, str]:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    m = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    role = await container.channel_repository.get_member_role(payload.channel_id, user.user_id)
    if role is None:
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    if m.sender_user_id != user.user_id and role != "owner":
        raise WsCommandError("forbidden", "Недостаточно прав на удаление.")
    now = datetime.now(tz=UTC)
    await container.message_repository.soft_delete_message(payload.message_id, now)
    ch = await container.channel_repository.get(payload.channel_id)
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    events: list[RealtimeEvent] = [
        event_message_deleted(
            payload.channel_id,
            payload.message_id,
            company_id=company_id,
            recipient_user_ids=recipients,
        ),
    ]
    if ch is not None:
        pids = list(ch.pinned_message_ids) if isinstance(ch.pinned_message_ids, list) else []
        if payload.message_id in pids:
            new_pids = [x for x in pids if x != payload.message_id]
            await container.channel_repository.set_pinned_message_ids(
                payload.channel_id, new_pids, company_id=company_id
            )
            ch2 = await container.channel_repository.get(payload.channel_id)
            if ch2 is not None:
                events.append(
                    event_channel_pins_changed(
                        _channel_read_entity(ch2),
                        company_id=company_id,
                        recipient_user_ids=recipients,
                    ),
                )
    await publish_realtime_events(events)
    return {"message_id": payload.message_id}


async def op_messages_forward(
    payload: MessagesForwardPayload,
    *,
    user: User,
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.from_channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к исходному каналу.")
    if not await container.channel_repository.is_member(
        payload.to_channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к целевому каналу.")
    m = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if m.channel_id != payload.from_channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Нельзя переслать удалённое сообщение.")
    content_rows = await container.message_repository.list_contents(m.message_id)
    contents = [
        MessageContentModel.model_validate(
            {"type": row.type, "data": row.data, "order": row.order}
        )
        for row in content_rows
    ]
    body = MessageCreate(
        thread_id=payload.thread_id,
        parent_message_id=None,
        contents=contents,
    )
    src_ch = await container.channel_repository.get(payload.from_channel_id)
    if src_ch is None:
        raise WsCommandError("not_found", "Исходный канал не найден.")
    raw_name = src_ch.name
    fwd_label = (
        raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() != "" else None
    )
    new_read = await _send_message(
        payload.to_channel_id,
        body,
        actor_user_id=user.user_id,
        company_id=company_id,
        messages=container.message_repository,
        user_repository=container.user_repository,
        forwarded_from_channel_id=payload.from_channel_id,
        forwarded_from_channel_name=fwd_label,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.to_channel_id, company_id
    )
    await publish_realtime_events(
        [
            event_message_created(
                new_read, company_id=company_id, recipient_user_ids=recipients
            ),
        ]
    )
    return new_read


def _apply_reaction_json(
    reactions_raw: object,
    actor_user_id: str,
    emoji: str | None,
    now: datetime,
) -> list[dict]:
    reactions = reactions_raw if isinstance(reactions_raw, list) else []
    filtered: list[dict] = []
    for r in reactions:
        if isinstance(r, dict) and r.get("user_id") != actor_user_id:
            filtered.append(r)
    if emoji is None:
        return filtered
    filtered.append(
        {"user_id": actor_user_id, "emoji": emoji, "created_at": now.isoformat()}
    )
    return filtered


async def op_messages_react(
    payload: MessagesReactPayload,
    *,
    user: User,
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    m = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Сообщение удалено.")
    now = datetime.now(tz=UTC)
    new_reactions = _apply_reaction_json(m.reactions, user.user_id, payload.emoji, now)
    await container.message_repository.set_message_reactions(payload.message_id, new_reactions)
    m2 = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise WsCommandError("internal", "Сообщение пропало после реакции.")
    read = await _message_read_from_db(
        m2, container.message_repository, container.user_repository
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> ChannelRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    role = await container.channel_repository.get_member_role(payload.channel_id, user.user_id)
    if role != "owner":
        raise WsCommandError("forbidden", "Закреплять может только владелец канала.")
    m = await container.message_repository.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if m.deleted_at is not None:
        raise WsCommandError("forbidden", "Нельзя закрепить удалённое сообщение.")
    ch = await container.channel_repository.get(payload.channel_id)
    if ch is None:
        raise WsCommandError("not_found", "Канал не найден.")
    pids = list(ch.pinned_message_ids) if isinstance(ch.pinned_message_ids, list) else []
    if payload.action == "add":
        if payload.message_id not in pids:
            pids.insert(0, payload.message_id)
    else:
        pids = [x for x in pids if x != payload.message_id]
    await container.channel_repository.set_pinned_message_ids(
        payload.channel_id, pids, company_id=company_id
    )
    ch2 = await container.channel_repository.get(payload.channel_id)
    if ch2 is None:
        raise WsCommandError("internal", "Канал пропал после обновления.")
    cr = _channel_read_entity(ch2)
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    source = await container.message_repository.get_by_id_for_company(
        payload.message_id, company_id
    )
    if source is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if source.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if source.deleted_at is not None:
        raise WsCommandError("forbidden", "Сообщение удалено.")
    source_rows = await container.message_repository.list_contents(payload.message_id)
    source_contents = [
        MessageContentModel.model_validate(
            {"type": row.type, "data": row.data, "order": row.order}
        )
        for row in source_rows
    ]
    processing_contents = _set_audio_transcription_state(
        source_contents,
        status=AudioTranscriptionStatus.PROCESSING,
        transcription_text=None,
        transcription_error=None,
    )
    edited_at = datetime.now(tz=UTC)
    await container.message_repository.replace_message_contents(
        payload.message_id, processing_contents, edited_at
    )
    updated_entity = await container.message_repository.get_by_id_for_company(
        payload.message_id, company_id
    )
    if updated_entity is None:
        raise WsCommandError("internal", "Сообщение пропало после запуска расшифровки.")
    updated_read = await _message_read_from_db(
        updated_entity, container.message_repository, container.user_repository
    )
    from apps.sync.realtime.tasks import sync_transcribe_audio_message_task

    await sync_transcribe_audio_message_task.kiq(
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        company_id=company_id,
        actor_user_id=user.user_id,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> MessageRead:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    source = await container.message_repository.get_by_id_for_company(
        payload.message_id, company_id
    )
    if source is None:
        raise WsCommandError("not_found", "Сообщение не найдено.")
    if source.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "Несовпадение канала.")
    if source.deleted_at is not None:
        raise WsCommandError("forbidden", "Сообщение удалено.")
    source_rows = await container.message_repository.list_contents(payload.message_id)
    source_contents = [
        MessageContentModel.model_validate(
            {"type": row.type, "data": row.data, "order": row.order}
        )
        for row in source_rows
    ]
    processing_contents = _set_video_transcription_state(
        source_contents,
        status=AudioTranscriptionStatus.PROCESSING,
        transcription_text=None,
        transcription_error=None,
    )
    edited_at = datetime.now(tz=UTC)
    await container.message_repository.replace_message_contents(
        payload.message_id, processing_contents, edited_at
    )
    updated_entity = await container.message_repository.get_by_id_for_company(
        payload.message_id, company_id
    )
    if updated_entity is None:
        raise WsCommandError("internal", "Сообщение пропало после запуска расшифровки.")
    updated_read = await _message_read_from_db(
        updated_entity, container.message_repository, container.user_repository
    )
    from apps.sync.realtime.tasks import sync_transcribe_video_message_task

    await sync_transcribe_video_message_task.kiq(
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        company_id=company_id,
        actor_user_id=user.user_id,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, payload.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> MessagesTranscribeCallResult:
    company_id = resolve_company_id(user)
    if not await container.channel_repository.is_member(
        payload.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к каналу.")
    call = await container.call_repository.get_call(payload.call_id, company_id)
    if call.channel_id != payload.channel_id:
        raise WsCommandError("forbidden", "call_id не относится к этому каналу.")
    from apps.sync.realtime.tasks import sync_aggregate_call_transcript_task

    await sync_aggregate_call_transcript_task.kiq(
        channel_id=payload.channel_id,
        call_id=payload.call_id,
        company_id=company_id,
        actor_user_id=user.user_id,
    )
    return MessagesTranscribeCallResult(status="queued")


# ===========================================================================
# Git resources
# ===========================================================================


class GitResourcesUpsertPayload(BaseModel):
    body: GitResourceRefCreate


class GitResourcesGetPayload(BaseModel):
    git_ref_id: str = Field(min_length=1)


async def op_git_resources_upsert(
    payload: GitResourcesUpsertPayload,
    *,
    user: User,
    container: SyncContainer,
) -> GitResourceRefRead:
    company_id = resolve_company_id(user)
    ref = await _upsert_git_resource(
        payload.body, company_id=company_id, git_refs=container.git_resource_ref_repository
    )
    await publish_realtime_events([event_git_resource_upserted(ref, company_id=company_id)])
    return ref


async def op_git_resources_get(
    payload: GitResourcesGetPayload,
    *,
    user: User,
    container: SyncContainer,
) -> GitResourceRefRead:
    _ = resolve_company_id(user)
    ref = await container.git_resource_ref_repository.get(payload.git_ref_id)
    if ref is None:
        raise WsCommandError("not_found", "Git resource not found")
    return GitResourceRefRead(
        id=ref.git_ref_id,
        provider=ref.provider,
        kind=ref.kind,
        project_key=ref.project_key,
        external_id=ref.external_id,
        url=ref.url,
        extra=ref.extra,
    )


# ===========================================================================
# Calls (mutating WS-команды)
# ===========================================================================


# Минимальный shim для совместимости с handle_call_invite/accept/decline/hangup
# (они принимают объект с полями actor_user_id / company_id / payload).
@dataclass(frozen=True)
class _CallCmdShim:
    actor_user_id: str
    company_id: str
    payload: dict[str, Any]


class CallsInvitePayload(BaseModel):
    channel_id: str = Field(min_length=1)


class CallsAcceptPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsDeclinePayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsHangupPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingStartPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingStopPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsAdminTransferPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)


class CallsSignalPayload(BaseModel):
    call_id: str = Field(min_length=1)
    target_user_id: str = Field(min_length=1)
    signal_type: SignalType
    data: dict[str, Any]


async def _post_call_boundary_message_op(
    *,
    channel_id: str,
    call_id: str,
    phase: Literal["started", "ended"],
    sender_user_id: str,
    company_id: str,
    container: SyncContainer,
) -> MessageRead:
    from apps.sync.models.messages import CallBoundaryContent

    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.CALL_BOUNDARY,
                data=CallBoundaryContent(call_id=call_id, phase=phase),
                order=0,
            )
        ],
        mentioned_user_ids=None,
        call_id=call_id,
    )
    return await _send_message(
        channel_id,
        body,
        actor_user_id=sender_user_id,
        company_id=company_id,
        messages=container.message_repository,
        user_repository=container.user_repository,
    )


async def op_calls_invite(
    payload: CallsInvitePayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    cmd = _CallCmdShim(
        actor_user_id=user.user_id,
        company_id=company_id,
        payload=payload.model_dump(),
    )
    out, evs = await handle_call_invite(
        cmd,
        calls=container.call_repository,
        channels=container.channel_repository,
        user_repository=container.user_repository,
    )
    member_ids = await container.channel_repository.list_member_user_ids(
        out.channel_id, company_id=company_id
    )
    started_read = await _post_call_boundary_message_op(
        channel_id=out.channel_id,
        call_id=out.call_id,
        phase="started",
        sender_user_id=out.created_by_user_id,
        company_id=company_id,
        container=container,
    )
    evs.append(
        event_message_created(
            started_read, company_id=company_id, recipient_user_ids=member_ids
        ),
    )
    if len(member_ids) <= 1:
        now = datetime.now(UTC)
        await container.call_repository.update_call_status(out.call_id, "active", started_at=now)
        solo_call = await container.call_repository.get_call(out.call_id, company_id)
        await _maybe_start_speech_to_chat_poll(
            call_id=solo_call.call_id,
            company_id=company_id,
            channel_id=solo_call.channel_id,
            livekit_room_name=solo_call.livekit_room_name,
            channels=container.channel_repository,
        )
    await publish_realtime_events(evs)
    return out


async def op_calls_accept(
    payload: CallsAcceptPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    cmd = _CallCmdShim(
        actor_user_id=user.user_id,
        company_id=company_id,
        payload=payload.model_dump(),
    )
    out, evs, became_active = await handle_call_accept(
        cmd, calls=container.call_repository, channels=container.channel_repository
    )
    if became_active:
        await _maybe_start_speech_to_chat_poll(
            call_id=out.call_id,
            company_id=company_id,
            channel_id=out.channel_id,
            livekit_room_name=out.livekit_room_name,
            channels=container.channel_repository,
        )
    await publish_realtime_events(evs)
    return out


async def op_calls_decline(
    payload: CallsDeclinePayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    cmd = _CallCmdShim(
        actor_user_id=user.user_id,
        company_id=company_id,
        payload=payload.model_dump(),
    )
    out, evs = await handle_call_decline(
        cmd, calls=container.call_repository, channels=container.channel_repository
    )
    await publish_realtime_events(evs)
    return out


async def op_calls_hangup(
    payload: CallsHangupPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    cmd = _CallCmdShim(
        actor_user_id=user.user_id,
        company_id=company_id,
        payload=payload.model_dump(),
    )

    auto_stopped_recording_event: RealtimeEvent | None = None
    call = await container.call_repository.get_call(payload.call_id, company_id)
    active_recording = await container.call_recording_repository.get_active_for_call(
        payload.call_id, company_id
    )
    if active_recording is not None and active_recording.started_by_user_id == user.user_id:
        stopped_recording = await _stop_and_finalize_recording(
            call=call,
            recording=active_recording,
            company_id=company_id,
            actor_user_id=user.user_id,
            call_recordings=container.call_recording_repository,
        )
        rec_stop_recipients = await _channel_recipient_user_ids(
            container.channel_repository, call.channel_id, company_id
        )
        auto_stopped_recording_event = event_call_recording_stopped(
            stopped_recording, company_id=company_id, recipient_user_ids=rec_stop_recipients
        )

    out, evs, fully_ended = await handle_call_hangup(
        cmd, calls=container.call_repository, channels=container.channel_repository
    )
    if auto_stopped_recording_event is not None:
        evs.append(auto_stopped_recording_event)
    if fully_ended:
        boundary_read = await _post_call_boundary_message_op(
            channel_id=out.channel_id,
            call_id=out.call_id,
            phase="ended",
            sender_user_id=out.created_by_user_id,
            company_id=company_id,
            container=container,
        )
        recipients = await _channel_recipient_user_ids(
            container.channel_repository, out.channel_id, company_id
        )
        evs.append(
            event_message_created(
                boundary_read, company_id=company_id, recipient_user_ids=recipients
            ),
        )
    await publish_realtime_events(evs)
    return out


async def op_calls_recording_start(
    payload: CallsRecordingStartPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRecordingRead:
    from apps.sync.db.models import SyncCallRecording

    company_id = resolve_company_id(user)
    call = await container.call_repository.get_call(payload.call_id, company_id)
    if call.status == "ended":
        raise WsCommandError("forbidden", "Нельзя включить запись завершённого звонка.")
    if call.created_by_user_id != user.user_id:
        raise WsCommandError("forbidden", "Только админ встречи может включать запись.")
    if call.livekit_room_name is None or call.livekit_room_name == "":
        raise WsCommandError(
            "forbidden", f"У звонка {call.call_id} отсутствует livekit_room_name."
        )
    if not await container.channel_repository.is_member(
        call.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к звонку.")
    active = await container.call_recording_repository.get_active_for_call(
        payload.call_id, company_id
    )
    if active is not None:
        raise WsCommandError("forbidden", "Запись уже запущена.")

    channel_entity = await container.channel_repository.get(call.channel_id)
    if channel_entity is None:
        raise WsCommandError("not_found", f"Канал {call.channel_id} не найден.")
    settings = get_settings()
    if settings.recording_max_duration_seconds <= 0:
        raise WsCommandError("internal", "recording_max_duration_seconds должен быть больше 0.")
    if not settings.s3.enabled:
        raise WsCommandError("internal", "S3 отключен: запись звонка в S3 недоступна.")
    default_bucket_key = settings.s3.default_bucket
    if default_bucket_key == "":
        raise WsCommandError("internal", "s3.default_bucket не настроен.")
    if default_bucket_key not in settings.s3.buckets:
        raise WsCommandError("internal", f"S3 bucket '{default_bucket_key}' не найден.")
    bucket_config = settings.s3.buckets[default_bucket_key]
    if not bucket_config.enabled:
        raise WsCommandError("internal", f"S3 bucket '{default_bucket_key}' выключен.")
    if not bucket_config.access_key_id:
        raise WsCommandError(
            "internal", f"S3 access_key_id не настроен для bucket '{default_bucket_key}'."
        )
    if not bucket_config.secret_access_key:
        raise WsCommandError(
            "internal",
            f"S3 secret_access_key не настроен для bucket '{default_bucket_key}'.",
        )
    if not bucket_config.region_name:
        raise WsCommandError(
            "internal", f"S3 region_name не настроен для bucket '{default_bucket_key}'."
        )
    real_bucket_name = bucket_config.bucket_name or default_bucket_key
    if real_bucket_name == "":
        raise WsCommandError("internal", "Имя S3 bucket для egress не может быть пустым.")
    recording_id = uuid4().hex
    egress_filepath = (
        f"sync-recordings/{company_id}/{call.call_id}/{recording_id}.mp4"
    )
    livekit_client = _build_livekit_recording_client()
    await livekit_client.create_room(
        call.livekit_room_name, company_id=company_id, user_id=user.user_id
    )
    egress_info = await livekit_client.start_room_composite_egress_to_s3(
        room_name=call.livekit_room_name,
        filepath=egress_filepath,
        s3_access_key=bucket_config.access_key_id,
        s3_secret_key=bucket_config.secret_access_key,
        s3_region=bucket_config.region_name,
        s3_bucket=real_bucket_name,
        company_id=company_id,
        user_id=user.user_id,
        s3_endpoint=_normalize_s3_egress_endpoint(bucket_config.endpoint_url),
        audio_only=(call.call_type == "audio"),
    )
    provider_job_id = getattr(egress_info, "egress_id", None)
    if not isinstance(provider_job_id, str) or provider_job_id == "":
        raise WsCommandError("internal", "LiveKit не вернул egress_id после старта записи.")
    recording = SyncCallRecording(
        recording_id=recording_id,
        call_id=call.call_id,
        company_id=company_id,
        channel_id=call.channel_id,
        namespace=channel_entity.namespace,
        status="recording",
        started_by_user_id=user.user_id,
        provider_job_id=provider_job_id,
        started_at=datetime.now(UTC),
    )
    await container.call_recording_repository.create(recording)
    out = CallRecordingRead(
        recording_id=recording.recording_id,
        call_id=recording.call_id,
        channel_id=recording.channel_id,
        namespace=recording.namespace,
        started_by_user_id=recording.started_by_user_id,
        status=recording.status,
        provider_job_id=recording.provider_job_id,
        raw_file_id=recording.raw_file_id,
        started_at=recording.started_at,
        ended_at=recording.ended_at,
        created_at=recording.created_at,
        error=recording.error,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, call.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> CallRecordingRead:
    company_id = resolve_company_id(user)
    call = await container.call_repository.get_call(payload.call_id, company_id)
    if not await container.channel_repository.is_member(
        call.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к звонку.")
    active = await container.call_recording_repository.get_active_for_call(
        payload.call_id, company_id
    )
    if active is None:
        raise WsCommandError("not_found", "Активная запись не найдена.")
    is_meeting_admin = call.created_by_user_id == user.user_id
    is_recording_starter = active.started_by_user_id == user.user_id
    if not is_meeting_admin and not is_recording_starter:
        raise WsCommandError(
            "forbidden",
            "Останавливать запись может только админ встречи или пользователь, который её запустил.",
        )
    out = await _stop_and_finalize_recording(
        call=call,
        recording=active,
        company_id=company_id,
        actor_user_id=user.user_id,
        call_recordings=container.call_recording_repository,
    )
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, call.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    call = await container.call_repository.get_call(payload.call_id, company_id)
    if call.created_by_user_id != user.user_id:
        raise WsCommandError(
            "forbidden", "Только текущий админ встречи может передавать админку."
        )
    if not await container.channel_repository.is_member(
        call.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к звонку.")
    if not await container.channel_repository.is_member(
        call.channel_id, payload.target_user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Новый админ не является участником канала.")
    if payload.target_user_id.startswith("guest:"):
        raise WsCommandError("forbidden", "Нельзя назначить гостя админом встречи.")
    participants = await container.call_repository.list_participants(call.call_id)
    target_participant = next(
        (item for item in participants if item.user_id == payload.target_user_id), None
    )
    if target_participant is None:
        raise WsCommandError("not_found", "Новый админ не найден среди участников звонка.")
    if target_participant.status != "joined":
        raise WsCommandError(
            "forbidden", "Новый админ должен быть активным участником звонка."
        )
    await container.call_repository.set_call_admin(call.call_id, payload.target_user_id)
    updated_call = await container.call_repository.get_call(call.call_id, company_id)
    updated_participants = await container.call_repository.list_participants(call.call_id)
    out = _call_read_from_entities(updated_call, updated_participants)
    recipients = await _channel_recipient_user_ids(
        container.channel_repository, out.channel_id, company_id
    )
    await publish_realtime_events(
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
    container: SyncContainer,
) -> None:
    """Быстрый путь сигналинга: без TaskIQ, прямая публикация события."""
    _ = container
    company_id = resolve_company_id(user)
    event = event_call_signal(
        payload.call_id,
        payload.signal_type,
        payload.data,
        company_id=company_id,
        recipient_user_ids=[payload.target_user_id],
    )
    event.payload["target_user_id"] = payload.target_user_id
    event.payload["sender_user_id"] = user.user_id
    await publish_realtime_events([event])
    return None


# ===========================================================================
# Calls (read + links + join)
# ===========================================================================


class CallsGetPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingsListPayload(BaseModel):
    call_id: str = Field(min_length=1)


class CallsRecordingsListResult(BaseModel):
    items: list[CallRecordingRead]


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


class CallsLinksListResult(BaseModel):
    items: list[CallScheduledLinkRead]
    total: int
    limit: int
    offset: int


class CallsLinksCreatePayload(BaseModel):
    body: CallLinkCreate


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


def _livekit_client(settings) -> LiveKitClient:
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )


def _livekit_public_url(settings) -> str:
    return settings.calls.livekit_public_url or settings.calls.livekit_url


def _ttl_hours_from_schedule(scheduled_end: datetime, now: datetime) -> int:
    delta = scheduled_end - now
    hours = int(delta.total_seconds() / 3600.0) + 2
    return max(1, min(168, hours))


async def _participant_names_for_call(
    container: SyncContainer, call: SyncCall
) -> dict[str, str]:
    out: dict[str, str] = {}
    member_ids = await container.channel_repository.list_member_user_ids(
        call.channel_id, company_id=call.company_id
    )
    for uid in member_ids:
        u = await container.user_repository.get(uid)
        out[uid] = u.name if u is not None else uid

    for p in await container.call_repository.list_participants(call.call_id):
        uid = p.user_id
        if uid in out:
            continue
        if uid.startswith("guest:"):
            parts = uid.split(":", 2)
            out[uid] = parts[2] if len(parts) >= 3 else "Гость"
        else:
            u = await container.user_repository.get(uid)
            out[uid] = u.name if u is not None else uid
    return out


async def _mint_join_short_url(
    container: SyncContainer, link_token: str, expires_at: datetime
) -> str:
    return await container.short_link_service.mint_sync_call_join(link_token, expires_at)


async def _reconcile_calendar_meeting_channel_members(
    *,
    container: SyncContainer,
    channel_id: str,
    company_id: str,
    link_creator_user_id: str,
    calendar_member_user_ids: list[str],
) -> None:
    channels = container.channel_repository
    desired_guests = {
        uid for uid in calendar_member_user_ids if uid and uid != link_creator_user_id
    }
    for uid in sorted(desired_guests):
        await channels.add_member_if_missing(channel_id, uid, "member", company_id=company_id)
    current = await channels.list_member_user_ids(channel_id, company_id=company_id)
    desired = {link_creator_user_id} | desired_guests
    for uid in current:
        if uid not in desired:
            await channels.delete_member(channel_id, uid, company_id=company_id)


async def op_calls_get(
    payload: CallsGetPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallRead:
    company_id = resolve_company_id(user)
    try:
        call = await container.call_repository.get_call(payload.call_id, company_id)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc
    participants = await container.call_repository.list_participants(payload.call_id)
    return _call_read_from_entities(call, participants)


async def op_calls_recordings_list(
    payload: CallsRecordingsListPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallsRecordingsListResult:
    company_id = resolve_company_id(user)
    call = await container.call_repository.get_call(payload.call_id, company_id)
    if not await container.channel_repository.is_member(
        call.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к звонку.")
    rows = await container.call_recording_repository.list_for_call(payload.call_id, company_id)
    items = [
        CallRecordingRead(
            recording_id=r.recording_id,
            call_id=r.call_id,
            channel_id=r.channel_id,
            namespace=r.namespace,
            started_by_user_id=r.started_by_user_id,
            status=r.status,
            provider_job_id=r.provider_job_id,
            raw_file_id=r.raw_file_id,
            started_at=r.started_at,
            ended_at=r.ended_at,
            created_at=r.created_at,
            error=r.error,
        )
        for r in rows
    ]
    return CallsRecordingsListResult(items=items)


async def op_calls_token(
    payload: CallsTokenPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallsTokenResult:
    company_id = resolve_company_id(user)
    settings = get_settings()
    try:
        call = await container.call_repository.get_call(payload.call_id, company_id)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc
    if call.mode != "sfu":
        raise WsCommandError(
            "forbidden", f"Звонок {payload.call_id} не является SFU-звонком."
        )
    if not call.livekit_room_name:
        raise WsCommandError(
            "forbidden", f"У звонка {payload.call_id} нет LiveKit комнаты."
        )
    if not await container.channel_repository.is_member(
        call.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError(
            "forbidden", f"Нет доступа к каналу звонка {payload.call_id}."
        )
    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name, identity=user.user_id
    )
    return CallsTokenResult(token=token, livekit_url=_livekit_public_url(settings))


async def op_calls_turn_credentials(
    payload: CallsTurnCredentialsPayload,
    *,
    user: User,
    container: SyncContainer,
) -> TurnCredentials:
    _ = payload
    _ = container
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
    container: SyncContainer,
) -> CallsLinksListResult:
    company_id = resolve_company_id(user)
    rows = await container.call_repository.list_scheduled_calendar_links_for_user(
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
        join_url = await _mint_join_short_url(container, row.link_token, row.expires_at)
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
    return CallsLinksListResult(
        items=page, total=len(out), limit=payload.limit, offset=payload.offset
    )


async def op_calls_links_create(
    payload: CallsLinksCreatePayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallLinkRead:
    company_id = resolve_company_id(user)
    body = payload.body
    actor_id = user.user_id

    channel_id: str
    attached_call_id: Optional[str] = None
    calendar_title: Optional[str] = None
    cal_start: Optional[datetime] = None
    cal_end: Optional[datetime] = None
    cal_event_id: Optional[str] = None
    ttl_hours = body.ttl_hours

    if body.calendar_event_id:
        dup = await container.call_repository.get_link_by_calendar_event(
            company_id, body.calendar_event_id
        )
        if dup is not None:
            raise WsCommandError(
                "conflict", "Для этого события календаря уже создана ссылка."
            )
        channel_id = uuid4().hex
        ch = SyncChannel(
            channel_id=channel_id,
            company_id=company_id,
            namespace="default",
            type=CHANNEL_TYPE_CALENDAR_MEETING,
            name=body.scheduled_title.strip(),
            is_private=False,
            created_at=datetime.now(UTC),
            created_by_user_id=actor_id,
            pinned_message_ids=[],
        )
        await container.channel_repository.create(ch)
        await container.channel_repository.add_member_if_missing(
            channel_id, actor_id, "owner", company_id=company_id
        )
        for uid in body.calendar_member_user_ids or []:
            if uid == actor_id:
                continue
            await container.channel_repository.add_member_if_missing(
                channel_id, uid, "member", company_id=company_id
            )
        now = datetime.now(UTC)
        ttl_hours = _ttl_hours_from_schedule(body.scheduled_end_at, now)
        expires_at = now + timedelta(hours=ttl_hours)
        calendar_title = body.scheduled_title.strip()
        cal_start = body.scheduled_start_at
        cal_end = body.scheduled_end_at
        cal_event_id = body.calendar_event_id
    else:
        if body.channel_id is None:
            raise WsCommandError(
                "ws_invalid_payload",
                "channel_id обязателен для ссылки без calendar_event_id.",
            )
        channel_id = body.channel_id
        if not await container.channel_repository.is_member(
            channel_id, actor_id, company_id=company_id
        ):
            raise WsCommandError("forbidden", "Нет доступа к каналу.")
        if body.call_id:
            try:
                existing = await container.call_repository.get_call(body.call_id, company_id)
            except ValueError as exc:
                raise WsCommandError("not_found", str(exc)) from exc
            if existing.channel_id != channel_id:
                raise WsCommandError(
                    "ws_invalid_payload", "Звонок относится к другому каналу."
                )
            if existing.status not in ("ringing", "active"):
                raise WsCommandError(
                    "forbidden",
                    "Ссылка на конференцию доступна только для активного или входящего звонка.",
                )
            if existing.mode != "sfu":
                raise WsCommandError(
                    "forbidden", "Гостевая ссылка поддерживается только для SFU-звонков."
                )
            if not existing.livekit_room_name:
                raise WsCommandError("forbidden", "У звонка нет LiveKit-комнаты.")
            attached_call_id = existing.call_id
        expires_at = datetime.now(UTC) + timedelta(hours=ttl_hours)

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
    )
    await container.call_repository.create_link(link)

    join_url = await _mint_join_short_url(container, link_token, expires_at)
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
    container: SyncContainer,
) -> CallLinkRead:
    company_id = resolve_company_id(user)
    body = payload.body
    link = await container.call_repository.get_link_for_company(
        payload.link_token, company_id
    )
    if link.calendar_event_id is None:
        raise WsCommandError(
            "forbidden", "Патч поддерживается только для календарных ссылок."
        )
    if not await container.channel_repository.is_member(
        link.channel_id, user.user_id, company_id=company_id
    ):
        raise WsCommandError("forbidden", "Нет доступа к ссылке.")

    new_start = body.scheduled_start_at if body.scheduled_start_at is not None else link.scheduled_start_at
    new_end = body.scheduled_end_at if body.scheduled_end_at is not None else link.scheduled_end_at
    if new_start is None or new_end is None:
        raise WsCommandError("ws_invalid_payload", "У ссылки должны быть границы расписания.")
    if new_start >= new_end:
        raise WsCommandError("ws_invalid_payload", "Некорректный интервал встречи.")

    new_title = body.scheduled_title if body.scheduled_title is not None else link.title
    now = datetime.now(UTC)
    new_expires = now + timedelta(hours=_ttl_hours_from_schedule(new_end, now))

    await container.call_repository.update_calendar_link(
        payload.link_token,
        company_id,
        title=new_title,
        scheduled_start_at=new_start,
        scheduled_end_at=new_end,
        expires_at=new_expires,
    )
    if body.scheduled_title is not None:
        ch = await container.channel_repository.get(link.channel_id)
        if ch is None or ch.company_id != company_id:
            raise WsCommandError("not_found", "Канал ссылки не найден.")
        name = body.scheduled_title.strip()
        if name == "":
            raise WsCommandError("ws_invalid_payload", "scheduled_title не может быть пустым.")
        ch.name = name
        await container.channel_repository.update(ch)
    if body.calendar_member_user_ids is not None:
        await _reconcile_calendar_meeting_channel_members(
            container=container,
            channel_id=link.channel_id,
            company_id=company_id,
            link_creator_user_id=link.created_by_user_id,
            calendar_member_user_ids=body.calendar_member_user_ids,
        )
    updated = await container.call_repository.get_link_for_company(payload.link_token, company_id)
    join_url = await _mint_join_short_url(container, payload.link_token, updated.expires_at)
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
    container: SyncContainer,
) -> None:
    company_id = resolve_company_id(user)
    link = await container.call_repository.get_link_for_company(payload.link_token, company_id)
    if link.calendar_event_id is None:
        raise WsCommandError(
            "forbidden", "Удаление через этот контракт только для календарных ссылок."
        )
    role = await container.channel_repository.get_member_role(link.channel_id, user.user_id)
    if link.created_by_user_id != user.user_id and role not in ("owner", "admin"):
        raise WsCommandError("forbidden", "Нет прав удалить эту ссылку.")
    channel_id = link.channel_id
    deleted = await container.call_repository.delete_link(payload.link_token, company_id)
    if not deleted:
        raise WsCommandError("not_found", "Ссылка не найдена.")
    await container.short_link_service.delete_sync_by_link_token(payload.link_token)
    ch = await container.channel_repository.get(channel_id)
    if ch is not None and ch.company_id == company_id and ch.type == CHANNEL_TYPE_CALENDAR_MEETING:
        await container.channel_repository.delete(channel_id)
    return None


async def op_calls_join_info(
    payload: CallsJoinInfoPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CallLinkInfo:
    _ = user
    try:
        link = await container.call_repository.get_link(payload.link_token)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc

    channel = await container.channel_repository.get(link.channel_id)
    channel_name = channel.name if channel else None

    creator_name = link.created_by_user_id
    creator_avatar_url: str | None = None
    creator = await container.user_repository.get(link.created_by_user_id)
    if creator is not None:
        creator_name = creator.name
        creator_avatar_url = creator.avatar_url

    return CallLinkInfo(
        link_token=payload.link_token,
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
    container: SyncContainer,
) -> JoinResponse:
    settings = get_settings()
    try:
        link = await container.call_repository.get_link(payload.link_token)
    except ValueError as exc:
        raise WsCommandError("not_found", str(exc)) from exc

    is_authenticated = user.user_id not in ("anonymous", "")

    identity: str
    if is_authenticated:
        identity = user.user_id
    else:
        if payload.body is None or not payload.body.guest_name.strip():
            raise WsCommandError(
                "ws_invalid_payload",
                "Для гостевого входа необходимо указать guest_name.",
            )
        safe_name = payload.body.guest_name.strip().replace(":", "_")
        identity = f"guest:{uuid4().hex[:8]}:{safe_name}"

    if link.call_id:
        call = await container.call_repository.get_call(link.call_id, link.company_id)
    else:
        livekit_room_name = f"link-{payload.link_token[:16]}"
        await _livekit_client(settings).create_room(
            livekit_room_name,
            company_id=link.company_id,
            user_id=identity,
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
        await container.call_repository.create_call(call)
        await container.call_repository.attach_call_to_link(payload.link_token, call.call_id)

    if not call.livekit_room_name:
        raise WsCommandError("internal", "У звонка нет LiveKit комнаты.")

    token = _livekit_client(settings).generate_token(
        room_name=call.livekit_room_name, identity=identity
    )
    participant_names = await _participant_names_for_call(container, call)

    return JoinResponse(
        call_id=call.call_id,
        call_type="video",
        livekit_token=token,
        livekit_url=_livekit_public_url(settings),
        identity=identity,
        meeting_admin_user_id=call.created_by_user_id,
        mode="sfu",
        participant_names=participant_names,
    )


# ===========================================================================
# Company members + shared channels
# ===========================================================================


class CompanyMembersListPayload(BaseModel):
    limit: int = Field(default=200, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class CompanyMembersListResult(BaseModel):
    items: list[CompanyMemberRead]
    total: int
    limit: int
    offset: int


class CompanySharedChannelsListPayload(BaseModel):
    peer_user_id: str = Field(min_length=1)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class CompanySharedChannelsListResult(BaseModel):
    items: list[ChannelRead]
    total: int
    limit: int
    offset: int


async def op_company_members_list(
    payload: CompanyMembersListPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CompanyMembersListResult:
    company_id = resolve_company_id(user)
    company = await container.company_repository.get(company_id)
    if company is None:
        raise WsCommandError("not_found", "Компания не найдена.")

    all_member_uids = [uid for uid in company.members if uid != user.user_id]
    total = len(all_member_uids)
    member_uids = all_member_uids[payload.offset : payload.offset + payload.limit]

    settings = get_settings()
    redis_url = settings.database.redis_url
    if not redis_url:
        raise WsCommandError("internal", "database.redis_url не задан.")

    presence_map, users_by_id = await asyncio.gather(
        batch_peer_presence(redis_url, member_uids),
        container.user_repository.get_many(member_uids),
    )

    items: list[CompanyMemberRead] = []
    for uid in member_uids:
        roles_raw = company.members[uid]
        member_user = users_by_id.get(uid)
        if member_user is None:
            raise WsCommandError(
                "internal",
                f"Участник {uid} указан в компании, но пользователь не найден.",
            )
        roles = list(roles_raw) if isinstance(roles_raw, list) else [roles_raw]
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
    return CompanyMembersListResult(
        items=items, total=total, limit=payload.limit, offset=payload.offset
    )


async def op_company_shared_channels_list(
    payload: CompanySharedChannelsListPayload,
    *,
    user: User,
    container: SyncContainer,
) -> CompanySharedChannelsListResult:
    company_id = resolve_company_id(user)
    company = await container.company_repository.get(company_id)
    if company is None:
        raise WsCommandError("not_found", "Компания не найдена.")
    if payload.peer_user_id not in company.members:
        raise WsCommandError("not_found", "Пользователь не в компании.")

    if payload.peer_user_id == user.user_id:
        channels = await container.channel_repository.list_for_user(
            user.user_id,
            namespace=None,
            limit=payload.limit,
            offset=payload.offset,
            company_id=company_id,
        )
    else:
        channels = await container.channel_repository.list_channels_where_both_members(
            user.user_id,
            payload.peer_user_id,
            limit=payload.limit,
            offset=payload.offset,
            company_id=company_id,
        )

    channel_ids = [c.channel_id for c in channels]
    summaries = await container.message_repository.channel_lane_summaries_batch(
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
                channel_repository=container.channel_repository,
                user_repository=container.user_repository,
                company_id=company_id,
                lane_summary=summaries[c.channel_id],
            )
        )
    return CompanySharedChannelsListResult(
        items=items, total=len(items), limit=payload.limit, offset=payload.offset
    )


# ===========================================================================
# Files (метаданные после REST upload)
# ===========================================================================


class FilesUploadCompletedPayload(BaseModel):
    file_id: str = Field(min_length=1)


class FilesUploadCompletedResult(BaseModel):
    file_id: str
    filename: str
    mime_type: str
    size: int


async def op_files_upload_completed(
    payload: FilesUploadCompletedPayload,
    *,
    user: User,
    container: SyncContainer,
) -> FilesUploadCompletedResult:
    """Подтверждение метаданных файла после REST multipart upload.

    Бинарный поток идёт через `POST /sync/api/v1/files/` (REST-only, multipart),
    а через WS клиент шлёт этот фрейм с `file_id`, чтобы получить
    каноничный `FilesUploadCompletedResult` для дальнейшей вставки в
    `MessagesSendPayload.body.contents`.
    """
    _ = user
    record: FileRecord | None = await container.file_repository.get(payload.file_id)
    if record is None:
        raise WsCommandError("not_found", f"Файл {payload.file_id!r} не найден.")
    return FilesUploadCompletedResult(
        file_id=record.file_id,
        filename=record.original_name,
        mime_type=record.content_type,
        size=record.file_size,
    )
