"""Сценарии команд сообщений Sync."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from apps.sync.events import (
    MessageStatusChangedPayload,
    event_channel_pins_changed,
    event_message_created,
    event_message_deleted,
    event_message_reaction_changed,
    event_message_status_changed,
    event_message_updated,
)
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.call import SyncCall
from apps.sync.models.call_participant import SyncCallParticipant
from apps.sync.models.channel import SyncChannel
from apps.sync.models.channels import ChannelRead, ChannelType
from apps.sync.models.common import UserBrief
from apps.sync.models.lane_preview import lane_preview_from_content
from apps.sync.models.message import SyncMessage
from apps.sync.models.message_content import SyncMessageContent
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageRead,
    MessageStatus,
    ReactionEntry,
    TextPlainContent,
)
from apps.sync.models.threads import SyncThread
from apps.sync.realtime.handlers import (
    channel_read_entity,
    channel_recipient_user_ids,
)
from apps.sync.realtime.task_names import (
    DELIVER_CHANNEL_MESSAGE_NOTIFICATION,
    DELIVER_SYNC_MENTION_NOTIFICATION,
    SYNC_AGGREGATE_CALL_TRANSCRIPT,
    SYNC_TRANSCRIBE_AUDIO_MESSAGE,
    SYNC_TRANSCRIBE_VIDEO_MESSAGE,
)
from apps.sync.sender_display import sender_brief_for_message
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.models import AuthzObject, AuthzSubject
from core.authz.service import AuthzService
from core.authz.types import AuthzRelation
from core.events import publish_events
from core.events.contract import PlatformEvent
from core.files.models import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    VideoAttachmentContent,
)
from core.identity.flow_employee import is_flow_employee
from core.models.identity_models import User
from core.pagination import CursorPage, OffsetPage
from core.request_scope import require_company
from core.tasks import enqueue
from core.types import JsonObject, parse_json_object
from core.websocket import WsCommandError


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


def _notification_preview_from_message(message: MessageRead) -> str:
    ordered = sorted(message.contents, key=lambda c: c.order)
    for c in ordered:
        if c.type == MessageContentType.TEXT_PLAIN:
            return lane_preview_from_content(c)
    if message.contents:
        c0 = sorted(message.contents, key=lambda c: c.order)[0]
        return lane_preview_from_content(c0)
    return "Новое сообщение"

async def _enqueue_channel_message_notifications(
    *,
    channel_id: str,
    body: MessageCreate,
    message: MessageRead,
    company_id: str,
    actor_user_id: str,
    channel_access: SyncChannelAccessService,
) -> None:
    entity = await SyncChannel.get(channel_id)
    if entity is None:
        raise ValueError(f"Channel {channel_id} not found.")
    preview = _notification_preview_from_message(message)
    is_direct = entity.type == ChannelType.DIRECT.value
    if is_direct:
        title = message.sender.display_name
    else:
        title = entity.name or "Канал"
    member_ids = await channel_access.list_member_user_ids(channel_id)
    mentioned: set[str] = set(message.mentioned_user_ids or [])
    is_root_lane = body.thread_id is None

    for uid in member_ids:
        if uid == actor_user_id:
            continue
        recipient = await User.get(uid)
        if recipient is not None and is_flow_employee(recipient):
            # Wake-up flow-сотрудника (DM/@mention) — consumer group `flows`
            # шины platform:events по событию sync/message/created; обычный
            # mention/channel toast сотруднику не шлётся.
            continue
        if uid in mentioned:
            _ = await enqueue(
                DELIVER_SYNC_MENTION_NOTIFICATION,
                recipient_user_id=uid,
                channel_id=channel_id,
                company_id=company_id,
                message_id=message.message_id,
                sender_display_name=message.sender.display_name,
                notification_title=title,
                body_preview=preview,
                background_kind="sync_notify",
            )
        elif is_root_lane:
            _ = await enqueue(
                DELIVER_CHANNEL_MESSAGE_NOTIFICATION,
                recipient_user_id=uid,
                channel_id=channel_id,
                company_id=company_id,
                message_id=message.message_id,
                sender_display_name=message.sender.display_name,
                notification_title=title,
                body_preview=preview,
                background_kind="sync_notify",
            )

async def _normalize_message_create_mentions(
    body: MessageCreate,
    *,
    channel_id: str,
    company_id: str,
    actor_user_id: str,
    channel_access: SyncChannelAccessService,
) -> MessageCreate:
    _ = company_id
    member_ids = set(
        await channel_access.list_member_user_ids(channel_id)
    )

    def validate_mention_ids(raw: list[str]) -> list[str]:
        ordered = list(dict.fromkeys(raw))
        for uid in ordered:
            if uid not in member_ids:
                raise ValueError(f"Mention: user {uid} is not a channel member.")
            if uid == actor_user_id:
                raise ValueError("Cannot mention yourself.")
        return ordered

    sorted_items = sorted(enumerate(body.contents), key=lambda t: t[1].order)
    first_text_idx: int | None = None
    for orig_idx, c in sorted_items:
        if c.type == MessageContentType.TEXT_PLAIN:
            first_text_idx = orig_idx
            break

    raw_mentions = body.mentioned_user_ids
    if raw_mentions is not None and len(raw_mentions) == 0:
        if first_text_idx is None:
            return MessageCreate(
                thread_id=body.thread_id,
                parent_message_id=body.parent_message_id,
                contents=body.contents,
                mentioned_user_ids=None,
                call_id=body.call_id,
            )
        c = body.contents[first_text_idx]
        if c.type != MessageContentType.TEXT_PLAIN:
            return MessageCreate(
                thread_id=body.thread_id,
                parent_message_id=body.parent_message_id,
                contents=body.contents,
                mentioned_user_ids=None,
                call_id=body.call_id,
            )
        d = c.data
        if not isinstance(d, TextPlainContent):
            raise ValueError("text/plain: expected TextPlainContent.")
        new_tp = TextPlainContent(body=d.body, mentions=None, origin=d.origin)
        new_contents: list[MessageContentModel] = []
        for i, x in enumerate(body.contents):
            if i == first_text_idx:
                new_contents.append(MessageContentModel(type=x.type, data=new_tp, order=x.order))
            else:
                new_contents.append(x)
        return MessageCreate(
            thread_id=body.thread_id,
            parent_message_id=body.parent_message_id,
            contents=new_contents,
            mentioned_user_ids=None,
            call_id=body.call_id,
        )

    if raw_mentions is None:
        if first_text_idx is None:
            return body
        c = body.contents[first_text_idx]
        d = c.data
        if not isinstance(d, TextPlainContent):
            raise ValueError("text/plain: expected TextPlainContent.")
        if d.mentions is None or len(d.mentions) == 0:
            return body
        mids = validate_mention_ids(list(d.mentions))
        new_tp = TextPlainContent(body=d.body, mentions=mids, origin=d.origin)
        new_contents = []
        for i, x in enumerate(body.contents):
            if i == first_text_idx:
                new_contents.append(MessageContentModel(type=x.type, data=new_tp, order=x.order))
            else:
                new_contents.append(x)
        return MessageCreate(
            thread_id=body.thread_id,
            parent_message_id=body.parent_message_id,
            contents=new_contents,
            mentioned_user_ids=None,
            call_id=body.call_id,
        )

    if first_text_idx is None:
        raise ValueError("Mentions require a text/plain block.")
    mids = validate_mention_ids(list(raw_mentions))
    c = body.contents[first_text_idx]
    d = c.data
    if not isinstance(d, TextPlainContent):
        raise ValueError("text/plain: expected TextPlainContent.")
    new_tp = TextPlainContent(body=d.body, mentions=mids, origin=d.origin)
    new_contents = []
    for i, x in enumerate(body.contents):
        if i == first_text_idx:
            new_contents.append(MessageContentModel(type=x.type, data=new_tp, order=x.order))
        else:
            new_contents.append(x)
    return MessageCreate(
        thread_id=body.thread_id,
        parent_message_id=body.parent_message_id,
        contents=new_contents,
        mentioned_user_ids=None,
        call_id=body.call_id,
    )

def _find_first_audio_content_index(contents: list[MessageContentModel]) -> int | None:
    sorted_items = sorted(enumerate(contents), key=lambda t: t[1].order)
    for original_index, content in sorted_items:
        if content.type == MessageContentType.FILE_AUDIO:
            return original_index
    return None

def set_audio_transcription_state(
    contents: list[MessageContentModel],
    *,
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    audio_index = _find_first_audio_content_index(contents)
    if audio_index is None:
        raise ValueError("Message has no file/audio content.")
    next_contents: list[MessageContentModel] = []
    for index, block in enumerate(contents):
        if index != audio_index:
            next_contents.append(block)
            continue
        if not isinstance(block.data, AudioAttachmentContent):
            raise ValueError("file/audio: expected AudioAttachmentContent.")
        next_audio = AudioAttachmentContent(
            file_id=block.data.file_id,
            original_name=block.data.original_name,
            content_type=block.data.content_type,
            file_size=block.data.file_size,
            duration_ms=block.data.duration_ms,
            waveform=block.data.waveform,
            transcription_status=status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
            source_speech_to_chat=block.data.source_speech_to_chat,
        )
        next_contents.append(
            MessageContentModel(type=block.type, data=next_audio, order=block.order)
        )
    return next_contents

def _find_first_video_content_index(contents: list[MessageContentModel]) -> int | None:
    sorted_items = sorted(enumerate(contents), key=lambda t: t[1].order)
    for original_index, content in sorted_items:
        if content.type == MessageContentType.FILE_VIDEO:
            return original_index
    return None

def set_video_transcription_state(
    contents: list[MessageContentModel],
    *,
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    video_index = _find_first_video_content_index(contents)
    if video_index is None:
        raise ValueError("Message has no file/video content.")
    next_contents: list[MessageContentModel] = []
    for index, block in enumerate(contents):
        if index != video_index:
            next_contents.append(block)
            continue
        if not isinstance(block.data, VideoAttachmentContent):
            raise ValueError("file/video: expected VideoAttachmentContent.")
        next_video = VideoAttachmentContent(
            file_id=block.data.file_id,
            original_name=block.data.original_name,
            content_type=block.data.content_type,
            file_size=block.data.file_size,
            duration_ms=block.data.duration_ms,
            transcription_status=status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
        )
        next_contents.append(
            MessageContentModel(type=block.type, data=next_video, order=block.order)
        )
    return next_contents

def _contents_include_speech_to_chat_audio(contents: list[MessageContentModel]) -> bool:
    for block in contents:
        if block.type != MessageContentType.FILE_AUDIO:
            continue
        if not isinstance(block.data, AudioAttachmentContent):
            raise ValueError("file/audio: expected AudioAttachmentContent.")
        if block.data.source_speech_to_chat:
            return True
    return False

async def ensure_actor_may_send_to_channel(
    *,
    channel_id: str,
    company_id: str,
    actor_user_id: str,
    body: MessageCreate,
    authz: AuthzService,
) -> None:
    if _contents_include_speech_to_chat_audio(body.contents):
        if body.call_id is None:
            raise PermissionError("speech-to-chat: call_id is required on the message.")
        call = await SyncCall.require_company_call(body.call_id, company_id)
        if call.channel_id != channel_id:
            raise ValueError("call_id does not belong to this channel.")
        return

    # guest:* — не OpenFGA user id (`user:guest:...` invalid); доступ только через call.
    if actor_user_id.startswith("guest:"):
        if body.call_id is None:
            raise PermissionError("Guest message requires call_id.")
        call = await SyncCall.require_company_call(body.call_id, company_id)
        if call.channel_id != channel_id:
            raise ValueError("call_id does not belong to this channel.")
        if call.status not in ("ringing", "active"):
            raise PermissionError("Call is not active.")
        participants = await SyncCallParticipant.list_for_call(body.call_id)
        mine = next((p for p in participants if p.user_id == actor_user_id), None)
        if mine is None or mine.status != "joined":
            raise PermissionError("Guest is not in this call.")
        return

    is_member = await authz.can_view(
        AuthzObject.sync_channel(channel_id), user_id=actor_user_id
    )
    if not is_member:
        raise PermissionError(f"User is not a member of channel {channel_id}.")
    if body.call_id is None:
        return
    call = await SyncCall.require_company_call(body.call_id, company_id)
    if call.channel_id != channel_id:
        raise ValueError("call_id does not belong to this channel.")

async def message_read_from_db(
    m: SyncMessage,
    *,
    resolve_user: bool,
) -> MessageRead:
    contents = await SyncMessageContent.list_for_message(m.message_id)
    sender = await sender_brief_for_message(m.sender_user_id, resolve_user=resolve_user)
    return message_read_from_entity(m=m, contents=contents, sender=sender)

async def send_message(
    channel_id: str,
    body: MessageCreate,
    *,
    actor_user_id: str,
    company_id: str,
    resolve_user: bool = False,
    forwarded_from_channel_id: str | None = None,
    forwarded_from_channel_name: str | None = None,
) -> MessageRead:
    message_id = uuid4().hex
    sent_at = datetime.now(tz=UTC)
    row = await SyncMessage.create_with_contents(
        message_id=message_id,
        company_id=company_id,
        channel_id=channel_id,
        thread_id=body.thread_id,
        parent_message_id=body.parent_message_id,
        call_id=body.call_id,
        sender_user_id=actor_user_id,
        status=MessageStatus.SENT.value,
        sent_at=sent_at,
        contents=body.contents,
        forwarded_from_channel_id=forwarded_from_channel_id,
        forwarded_from_channel_name=forwarded_from_channel_name,
    )
    return await message_read_from_db(row, resolve_user=resolve_user)

async def send_message_with_side_effects(
    *,
    channel_id: str,
    body: MessageCreate,
    user: User,
    authz: AuthzService,
    channel_access: SyncChannelAccessService,
) -> MessageRead:
    company_id = require_company().company_id
    await ensure_actor_may_send_to_channel(
        channel_id=channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        body=body,
        authz=authz,
    )
    normalized_body = await _normalize_message_create_mentions(
        body,
        channel_id=channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        channel_access=channel_access,
    )
    message = await send_message(
        channel_id,
        normalized_body,
        actor_user_id=user.user_id,
        company_id=company_id,
        resolve_user=True,
    )
    await _enqueue_channel_message_notifications(
        channel_id=channel_id,
        body=normalized_body,
        message=message,
        company_id=company_id,
        actor_user_id=user.user_id,
        channel_access=channel_access,
    )
    recipients = await channel_recipient_user_ids(
        channel_access, channel_id
    )
    channel_entity = await SyncChannel.get(channel_id)
    if channel_entity is None:
        raise WsCommandError("not_found", f"Channel {channel_id} not found.", error_code='not_found')
    created_event = event_message_created(
        message,
        company_id=company_id,
        recipient_user_ids=recipients,
        channel_type=channel_entity.type,
        local_id=body.local_id if body.local_id else None,
    )
    events: list[PlatformEvent] = [created_event]
    audio_idx = _find_first_audio_content_index(normalized_body.contents)
    if audio_idx is not None:
        block = normalized_body.contents[audio_idx]
        if isinstance(block.data, AudioAttachmentContent):
            enqueue_stt = (
                block.data.transcription_status == AudioTranscriptionStatus.IDLE
                and (
                    block.data.source_speech_to_chat
                    or channel_entity.transcribe_voice_messages
                )
            )
            if enqueue_stt:
                processing_contents = set_audio_transcription_state(
                    list(message.contents),
                    status=AudioTranscriptionStatus.PROCESSING,
                    transcription_text=None,
                    transcription_error=None,
                )
                edited_at = datetime.now(tz=UTC)
                await SyncMessage.replace_contents(
                    message.message_id, processing_contents, edited_at
                )
                proc_entity = await SyncMessage.find_in_company(
                    company_id, message.message_id
                )
                if proc_entity is None:
                    raise WsCommandError(
                        "internal", "Message disappeared after auto-transcription start.",
                              error_code='internal',
                          )
                message = await message_read_from_db(
                    proc_entity, resolve_user=True
                )
                events.append(
                    event_message_updated(
                        message,
                        company_id=company_id,
                        recipient_user_ids=recipients,
                    ),
                )
                _ = await enqueue(
                    SYNC_TRANSCRIBE_AUDIO_MESSAGE,
                    channel_id=channel_id,
                    message_id=message.message_id,
                    company_id=company_id,
                    actor_user_id=user.user_id,
                    background_kind="sync_transcribe",
                )
    await publish_events(events)
    return message

class SyncMessageService:
    """Команды сообщений: лента, правка, пересылка, реакции, закрепление, транскрипция."""

    def __init__(
        self,
        authz: AuthzService,
        channel_access: SyncChannelAccessService,
    ) -> None:
        self._authz: AuthzService = authz
        self._channel_access: SyncChannelAccessService = channel_access

    async def send(
        self,
        *,
        user: User,
        channel_id: str,
        body: MessageCreate,
    ) -> MessageRead:
        return await send_message_with_side_effects(
            channel_id=channel_id,
            body=body,
            user=user,
            authz=self._authz,
            channel_access=self._channel_access,
        )

    async def list_messages(
            self,
            *,
            company_id: str,
            channel_id: str,
            limit: int,
            before: str | None,
            after: str | None,
        ) -> CursorPage[MessageRead]:
        if before is not None and after is not None:
            raise WsCommandError(
                "ws_invalid_payload", "before and after are mutually exclusive",
                      error_code='ws_invalid_payload',
                  )

        before_sent_at: datetime | None = None
        before_message_id: str | None = None
        if before is not None and before != "":
            before_sent_at, before_message_id = _decode_message_cursor(before)
        after_sent_at: datetime | None = None
        after_message_id: str | None = None
        if after is not None and after != "":
            after_sent_at, after_message_id = _decode_message_cursor(after)

        window = await SyncMessage.list_root_lane_cursor(
            channel_id=channel_id,
            limit=limit,
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

    async def list_thread(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            thread_id: str,
            limit: int,
            offset: int,
        ) -> OffsetPage[MessageRead]:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "Not a channel member", error_code='forbidden')
        thread = await SyncThread.get(thread_id)
        if thread is None:
            raise WsCommandError("not_found", f"Thread {thread_id!r} not found.", error_code='not_found')
        if thread.channel_id != channel_id:
            raise WsCommandError(
                "ws_invalid_payload",
                "thread_id does not belong to channel_id",
                      error_code='ws_invalid_payload',
                  )
        rows = await SyncMessage.list_by_thread(
            thread_id=thread_id,
            limit=limit,
            offset=offset,
            company_id=company_id,
        )
        if not rows:
            return OffsetPage[MessageRead](
                items=[],
                total=0,
                limit=limit,
                offset=offset,
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
            limit=limit,
            offset=offset,
        )

    async def mark_read(
            self,
            *,
            company_id: str,
            channel_id: str,
            message_id: str,
        ) -> None:
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_message_status_changed(
                    channel_id,
                    MessageStatusChangedPayload(
                        message_id=message_id, status=MessageStatus.READ
                    ),
                    company_id=company_id,
                    recipient_user_ids=recipients,
                ),
            ]
        )
        return None

    async def edit_message(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
            contents: list[MessageContentModel],
        ) -> MessageRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        m = await SyncMessage.find_in_company(company_id, message_id)
        if m is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if m.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if m.deleted_at is not None:
            raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
        if m.sender_user_id != user_id:
            raise WsCommandError("forbidden", "Only the author can edit.", error_code='forbidden')
        edited_at = datetime.now(tz=UTC)
        await SyncMessage.replace_contents(
            message_id, contents, edited_at
        )
        m2 = await SyncMessage.find_in_company(company_id, message_id)
        if m2 is None:
            raise WsCommandError("internal", "Message disappeared after edit.", error_code='internal')
        read = await message_read_from_db(
            m2, resolve_user=True
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_message_updated(
                    read, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return read

    async def delete_message(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
        ) -> None:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        m = await SyncMessage.find_in_company(company_id, message_id)
        if m is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if m.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if m.sender_user_id != user_id and not await self._authz.check(
            AuthzSubject.user(user_id),
            AuthzRelation.OWNER,
            AuthzObject.sync_channel(channel_id),
        ):
            raise WsCommandError("forbidden", "Insufficient permission to delete.", error_code='forbidden')
        now = datetime.now(tz=UTC)
        await SyncMessage.soft_delete(message_id, now)
        ch = await SyncChannel.get(channel_id)
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        events: list[PlatformEvent] = [
            event_message_deleted(
                channel_id,
                message_id,
                company_id=company_id,
                recipient_user_ids=recipients,
            ),
        ]
        if ch is not None:
            pids = list(ch.pinned_message_ids)
            if message_id in pids:
                new_pids = [x for x in pids if x != message_id]
                await SyncChannel.set_channel_pinned_message_ids(
                    channel_id,
                    new_pids,
                    company_id=company_id,
                )
                ch2 = await SyncChannel.get(channel_id)
                if ch2 is not None:
                    events.append(
                        event_channel_pins_changed(
                            channel_read_entity(ch2),
                            company_id=company_id,
                            recipient_user_ids=recipients,
                        ),
                    )
        await publish_events(events)
        return None

    async def forward_message(
            self,
            *,
            company_id: str,
            user_id: str,
            from_channel_id: str,
            message_id: str,
            to_channel_id: str,
            thread_id: str | None,
        ) -> MessageRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(from_channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the source channel.", error_code='forbidden')
        if not await self._authz.can_view(
            AuthzObject.sync_channel(to_channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to the target channel.", error_code='forbidden')
        m = await SyncMessage.find_in_company(company_id, message_id)
        if m is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if m.channel_id != from_channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if m.deleted_at is not None:
            raise WsCommandError("forbidden", "Cannot forward a deleted message.", error_code='forbidden')
        contents = await SyncMessageContent.list_for_message(m.message_id)
        body = MessageCreate(
            thread_id=thread_id,
            parent_message_id=None,
            contents=contents,
        )
        src_ch = await SyncChannel.get(from_channel_id)
        if src_ch is None:
            raise WsCommandError("not_found", "Source channel not found.", error_code='not_found')
        raw_name = src_ch.name
        fwd_label = (
            raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() != "" else None
        )
        new_read = await send_message(
            to_channel_id,
            body,
            actor_user_id=user_id,
            company_id=company_id,
            resolve_user=True,
            forwarded_from_channel_id=from_channel_id,
            forwarded_from_channel_name=fwd_label,
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, to_channel_id
        )
        dst_ch = await SyncChannel.get(to_channel_id)
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

    async def react(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
            emoji: str | None,
        ) -> MessageRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        m = await SyncMessage.find_in_company(company_id, message_id)
        if m is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if m.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if m.deleted_at is not None:
            raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
        now = datetime.now(tz=UTC)
        new_reactions = _apply_reaction_json(m.reactions, user_id, emoji, now)
        await SyncMessage.set_reactions(message_id, new_reactions)
        m2 = await SyncMessage.find_in_company(company_id, message_id)
        if m2 is None:
            raise WsCommandError("internal", "Message disappeared after reaction.", error_code='internal')
        read = await message_read_from_db(
            m2, resolve_user=True
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_message_reaction_changed(
                    channel_id,
                    message_id,
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

    async def pin(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
            action: Literal["add", "remove"],
        ) -> ChannelRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        if not await self._authz.check(
            AuthzSubject.user(user_id),
            AuthzRelation.OWNER,
            AuthzObject.sync_channel(channel_id),
        ):
            raise WsCommandError("forbidden", "Only the channel owner can pin.", error_code='forbidden')
        m = await SyncMessage.find_in_company(company_id, message_id)
        if m is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if m.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if m.deleted_at is not None:
            raise WsCommandError("forbidden", "Cannot pin a deleted message.", error_code='forbidden')
        ch = await SyncChannel.get(channel_id)
        if ch is None:
            raise WsCommandError("not_found", "Channel not found.", error_code='not_found')
        pids = list(ch.pinned_message_ids)
        if action == "add":
            if message_id not in pids:
                pids.insert(0, message_id)
        else:
            pids = [x for x in pids if x != message_id]
        await SyncChannel.set_channel_pinned_message_ids(
            channel_id,
            pids,
            company_id=company_id,
        )
        ch2 = await SyncChannel.get(channel_id)
        if ch2 is None:
            raise WsCommandError("internal", "Channel disappeared after update.", error_code='internal')
        cr = channel_read_entity(ch2)
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_channel_pins_changed(
                    cr, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return cr

    async def transcribe_audio(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
        ) -> MessageRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        source = await SyncMessage.find_in_company(
            company_id, message_id
        )
        if source is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if source.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if source.deleted_at is not None:
            raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
        source_contents = await SyncMessageContent.list_for_message(message_id)
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
            message_id, processing_contents, edited_at
        )
        updated_entity = await SyncMessage.find_in_company(
            company_id, message_id
        )
        if updated_entity is None:
            raise WsCommandError("internal", "Message disappeared after transcription start.", error_code='internal')
        updated_read = await message_read_from_db(
            updated_entity, resolve_user=True
        )
        _ = await enqueue(
            SYNC_TRANSCRIBE_AUDIO_MESSAGE,
            channel_id=channel_id,
            message_id=message_id,
            company_id=company_id,
            actor_user_id=user_id,
            background_kind="sync_transcribe",
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_message_updated(
                    updated_read, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return updated_read

    async def transcribe_video(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            message_id: str,
        ) -> MessageRead:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        source = await SyncMessage.find_in_company(
            company_id, message_id
        )
        if source is None:
            raise WsCommandError("not_found", "Message not found.", error_code='not_found')
        if source.channel_id != channel_id:
            raise WsCommandError("forbidden", "Channel mismatch.", error_code='forbidden')
        if source.deleted_at is not None:
            raise WsCommandError("forbidden", "Message is deleted.", error_code='forbidden')
        source_contents = await SyncMessageContent.list_for_message(message_id)
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
            message_id, processing_contents, edited_at
        )
        updated_entity = await SyncMessage.find_in_company(
            company_id, message_id
        )
        if updated_entity is None:
            raise WsCommandError("internal", "Message disappeared after transcription start.", error_code='internal')
        updated_read = await message_read_from_db(
            updated_entity, resolve_user=True
        )
        _ = await enqueue(
            SYNC_TRANSCRIBE_VIDEO_MESSAGE,
            channel_id=channel_id,
            message_id=message_id,
            company_id=company_id,
            actor_user_id=user_id,
            background_kind="sync_transcribe",
        )
        recipients = await channel_recipient_user_ids(
            self._channel_access, channel_id
        )
        await publish_events(
            [
                event_message_updated(
                    updated_read, company_id=company_id, recipient_user_ids=recipients
                ),
            ]
        )
        return updated_read

    async def transcribe_call(
            self,
            *,
            company_id: str,
            user_id: str,
            channel_id: str,
            call_id: str,
        ) -> None:
        if not await self._authz.can_view(
            AuthzObject.sync_channel(channel_id), user_id=user_id
        ):
            raise WsCommandError("forbidden", "No access to channel.", error_code='forbidden')
        call = await SyncCall.require_company_call(call_id, company_id)
        if call.channel_id != channel_id:
            raise WsCommandError("forbidden", "call_id does not belong to this channel.", error_code='forbidden')
        _ = await enqueue(
            SYNC_AGGREGATE_CALL_TRANSCRIPT,
            channel_id=channel_id,
            call_id=call_id,
            company_id=company_id,
            actor_user_id=user_id,
            background_kind="sync_transcribe",
        )
        return None
