"""Внутренние helpers Sync.

Это внутренняя библиотека функций (`create_channel`, `send_message`, …),
которыми пользуются `op_*` из `apps/sync/realtime/operations.py`. Никаких
веток `if cmd.type == ...` и никаких `CommandEnvelope` / `execute_command`
здесь нет — единый pipeline команд живёт в `operations.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import uuid4

from livekit.api.twirp_client import TwirpError, TwirpErrorCode

from apps.sync.channel_lane_preview import lane_preview_from_content
from apps.sync.channel_read_helpers import channel_read_entity_minimal, channel_read_from_entity
from apps.sync.db.models import (
    SyncCall,
    SyncCallRecording,
    SyncChannel,
    SyncGitResourceRef,
    SyncMessage,
    SyncThread,
)
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.meeting_repository import (
    CallRecordingRepository,
    call_recording_read,
)
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.events import (
    event_message_created,
    event_message_updated,
)
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.channels import ChannelCreate, ChannelRead, ChannelType, ChannelUpdate
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefCreate, GitResourceRefRead
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageRead,
    MessageStatus,
    TextPlainContent,
)
from apps.sync.models.threads import ThreadCreate, ThreadRead
from apps.sync.realtime.task_names import (
    DELIVER_CHANNEL_MESSAGE_NOTIFICATION,
    DELIVER_SYNC_MENTION_NOTIFICATION,
    SYNC_FINALIZE_RECORDING,
    SYNC_SPEECH_TO_CHAT_POLL,
    SYNC_TRANSCRIBE_AUDIO_MESSAGE,
)
from apps.sync.sender_display import sender_brief_for_message
from apps.sync.services.sync_channel_access_service import SyncChannelAccessService
from core.authz.models import AuthzObject
from core.authz.service import AuthzService
from core.calls.livekit_client import LiveKitClient
from core.calls.livekit_usage_spans import trace_livekit_egress_composite_usage
from core.config import get_settings
from core.db.repositories.user_repository import UserRepository
from core.events import publish_events
from core.events.contract import PlatformEvent
from core.files.models import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    VideoAttachmentContent,
)
from core.identity.flow_employee import is_flow_employee
from core.logging import get_logger
from core.namespace import NamespaceService
from core.request_scope import require_company
from core.tasks import enqueue
from core.websocket import WsCommandError

logger = get_logger(__name__)


if TYPE_CHECKING:
    from apps.sync.container import SyncContainer
    from core.models.identity_models import User


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
    channels: ChannelRepository,
) -> None:
    if livekit_room_name is None or livekit_room_name == "":
        return
    ch = await channels.get(channel_id)
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


def normalize_s3_egress_endpoint(endpoint_url: str | None) -> str | None:
    if endpoint_url is None:
        return None
    trimmed = endpoint_url.strip()
    if trimmed == "":
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme == "":
        return trimmed
    if parsed.netloc == "":
        raise ValueError(f"Invalid endpoint_url for S3 egress: {endpoint_url}")
    hostname = parsed.hostname
    if hostname is None or hostname == "":
        raise ValueError(f"Invalid hostname in endpoint_url for S3 egress: {endpoint_url}")
    if hostname == "localhost" or hostname == "127.0.0.1":
        hostname = "host.docker.internal"
    if parsed.port is None:
        netloc = hostname
    else:
        netloc = f"{hostname}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"


def build_livekit_recording_client() -> LiveKitClient:
    settings = get_settings()
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )


async def stop_and_finalize_recording(
    *,
    call: SyncCall,
    recording: SyncCallRecording,
    company_id: str,
    actor_user_id: str,
    call_recordings: CallRecordingRepository,
) -> CallRecordingRead:
    if recording.provider_job_id is None or recording.provider_job_id == "":
        raise ValueError(
            f"Recording {recording.recording_id} has no provider_job_id; cannot stop egress."
        )
    settings = get_settings()
    if settings.recording_max_duration_seconds <= 0:
        raise ValueError("recording_max_duration_seconds must be greater than 0.")
    if recording.started_at is not None:
        max_end_at = recording.started_at + timedelta(seconds=settings.recording_max_duration_seconds)
        logger.info(
            "call.recording.stop",
            call_id=call.call_id,
            recording_id=recording.recording_id,
            started_at=recording.started_at.isoformat(),
            max_end_at=max_end_at.isoformat(),
            now=datetime.now(UTC).isoformat(),
        )
    livekit_client = build_livekit_recording_client()
    logger.info(
        "call.recording.stop",
        call_id=call.call_id,
        recording_id=recording.recording_id,
        egress_id=recording.provider_job_id,
    )
    try:
        _ = await livekit_client.stop_egress(
            egress_id=recording.provider_job_id,
            company_id=company_id,
            user_id=actor_user_id,
        )
    except TwirpError as exc:
        if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
            logger.warning(
                "call.recording.stop",
                call_id=call.call_id,
                recording_id=recording.recording_id,
                egress_id=recording.provider_job_id,
                code=exc.code,
                message=str(exc),
            )
        else:
            raise
    await call_recordings.mark_status(
        recording.recording_id,
        status="uploaded",
        ended_at=datetime.now(UTC),
    )
    updated_recording = await call_recordings.get(recording.recording_id)
    if updated_recording is None:
        raise RuntimeError("Recording disappeared after update.")
    if call.livekit_room_name is not None and call.livekit_room_name != "":
        if recording.started_by_user_id is None:
            raise RuntimeError("Recording started_by_user_id is required for egress billing trace")
        await trace_livekit_egress_composite_usage(
            company_id=company_id,
            user_id=recording.started_by_user_id,
            call_id=call.call_id,
            recording_id=updated_recording.recording_id,
            livekit_room_name=call.livekit_room_name,
            egress_id=recording.provider_job_id,
            started_at=recording.started_at,
            ended_at=updated_recording.ended_at,
        )
    _ = await enqueue(
        SYNC_FINALIZE_RECORDING,
        recording_id=updated_recording.recording_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
        background_kind="sync_call",
    )
    return call_recording_read(updated_recording)


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
    channels: ChannelRepository,
    channel_access: SyncChannelAccessService,
    user_repository: UserRepository,
) -> None:
    entity = await channels.get(channel_id)
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
        recipient = await user_repository.get(uid)
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


async def _ensure_actor_may_send_to_channel(
    *,
    channel_id: str,
    company_id: str,
    actor_user_id: str,
    body: MessageCreate,
    authz: AuthzService,
    calls: CallRepository | None,
) -> None:
    if _contents_include_speech_to_chat_audio(body.contents):
        if body.call_id is None:
            raise PermissionError("speech-to-chat: call_id is required on the message.")
        if calls is None:
            raise RuntimeError("CallRepository is required for speech-to-chat.")
        call = await calls.get_call(body.call_id, company_id)
        if call.channel_id != channel_id:
            raise ValueError("call_id does not belong to this channel.")
        return

    # guest:* — не OpenFGA user id (`user:guest:...` invalid); доступ только через call.
    if actor_user_id.startswith("guest:"):
        if body.call_id is None:
            raise PermissionError("Guest message requires call_id.")
        if calls is None:
            raise RuntimeError("CallRepository is required for guest messages.")
        call = await calls.get_call(body.call_id, company_id)
        if call.channel_id != channel_id:
            raise ValueError("call_id does not belong to this channel.")
        if call.status not in ("ringing", "active"):
            raise PermissionError("Call is not active.")
        participants = await calls.list_participants(body.call_id)
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
    if calls is None:
        raise RuntimeError("CallRepository is required when the message has call_id.")
    call = await calls.get_call(body.call_id, company_id)
    if call.channel_id != channel_id:
        raise ValueError("call_id does not belong to this channel.")


async def _user_brief(user_repository: UserRepository | None, user_id: str) -> UserBrief:
    display_name = user_id
    avatar_url = None
    if user_repository is not None:
        u = await user_repository.get(user_id)
        if u is not None:
            display_name = u.name
            avatar_url = u.avatar_url
    return UserBrief(user_id=user_id, display_name=display_name, avatar_url=avatar_url)


async def message_read_from_db(
    m: SyncMessage,
    messages: MessageRepository,
    user_repository: UserRepository | None,
) -> MessageRead:
    contents = await messages.list_contents(m.message_id)
    sender = await sender_brief_for_message(user_repository, m.sender_user_id)
    return message_read_from_entity(m=m, contents=contents, sender=sender)


def channel_read_entity(entity: SyncChannel) -> ChannelRead:
    return channel_read_entity_minimal(entity)


async def _channel_read_for_viewer(
    entity: SyncChannel,
    *,
    viewer_user_id: str,
    company_id: str,
    channels: ChannelRepository,
    channel_access: SyncChannelAccessService,
    user_repository: UserRepository,
) -> ChannelRead:
    """ChannelRead для ответа create/list: direct с заполненным peer."""
    return await channel_read_from_entity(
        entity,
        viewer_user_id=viewer_user_id,
        channel_repository=channels,
        channel_access=channel_access,
        user_repository=user_repository,
        company_id=company_id,
        lane_summary=None,
    )


async def update_channel(
    channel_id: str,
    body: ChannelUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    channels: ChannelRepository,
    authz: AuthzService,
) -> ChannelRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise WsCommandError("ws_invalid_payload", "No fields to update on the channel.", error_code='ws_invalid_payload')
    if not await authz.can_view(
        AuthzObject.sync_channel(channel_id), user_id=actor_user_id
    ):
        raise WsCommandError("forbidden", f"User is not a member of channel {channel_id}.", error_code='forbidden')
    if not await authz.can_admin(
        AuthzObject.sync_channel(channel_id), user_id=actor_user_id
    ):
        raise WsCommandError(
            "forbidden",
            "Channel settings can be changed only by owner and admin roles.",
                  error_code='forbidden',
              )
    entity = await channels.get(channel_id)
    if entity is None:
        raise WsCommandError("not_found", f"Channel {channel_id} not found.", error_code='not_found')
    if entity.company_id != company_id:
        raise WsCommandError("forbidden", "Channel belongs to another company.", error_code='forbidden')
    if "name" in data:
        entity.name = data["name"]
    if "is_private" in data:
        entity.is_private = data["is_private"]
    if "avatar_url" in data:
        entity.avatar_url = data["avatar_url"]
    if "transcribe_voice_messages" in data:
        entity.transcribe_voice_messages = data["transcribe_voice_messages"]
    if "speech_to_chat_enabled" in data:
        entity.speech_to_chat_enabled = data["speech_to_chat_enabled"]
    _ = await channels.update(entity)
    return channel_read_entity(entity)


async def _find_existing_direct_for_pair(
    *,
    user_a: str,
    user_b: str,
    namespace: str,
    company_id: str,
    channels: ChannelRepository,
    channel_access: SyncChannelAccessService,
) -> SyncChannel | None:
    """Один личный чат с собеседником в рамках namespace (без дублей create)."""
    candidates = await channels.list_channels_where_both_members(
        user_a, user_b, company_id=company_id
    )
    for ch in candidates:
        if ch.type != ChannelType.DIRECT.value:
            continue
        if ch.namespace != namespace:
            continue
        member_ids = await channel_access.list_member_user_ids(ch.channel_id)
        if len(member_ids) == 2:
            return ch
    return None


async def create_channel(
    body: ChannelCreate,
    *,
    actor_user_id: str,
    company_id: str,
    channels: ChannelRepository,
    channel_access: SyncChannelAccessService,
    namespaces: NamespaceService,
    user_repository: UserRepository,
) -> tuple[ChannelRead, bool]:
    """Создаёт канал, привязанный к платформенному `namespace`.

    Дефолты STT (`transcribe_voice_messages`, `speech_to_chat_enabled`)
    берутся из `Namespace.sync_settings`; на канале можно перекрыть точечно
    через `body.transcribe_voice_messages` / `body.speech_to_chat_enabled`.

    Возвращает (ChannelRead, created_new). Для direct с тем же собеседником
    и namespace возвращается существующий канал с created_new=False (без дублей).
    """
    if body.type == ChannelType.TOPIC:
        if body.namespace is None or body.namespace == "":
            raise ValueError("topic requires namespace.")
        if body.name is None:
            raise ValueError("topic requires name.")

    if body.type == ChannelType.DIRECT:
        mids = body.member_ids
        if mids is None or len(mids) != 1:
            raise ValueError("direct requires exactly one peer in member_ids.")
        if mids[0] == actor_user_id:
            raise ValueError("Cannot create a direct channel with yourself.")

    if body.type == ChannelType.CALENDAR_MEETING:
        if body.name is None or body.name.strip() == "":
            raise ValueError("calendar_meeting requires name (meeting title).")

    namespace = body.namespace if body.namespace else "default"
    ns_entity = await namespaces.ensure_exists(namespace)
    if ns_entity.company_id != company_id:
        raise PermissionError(f"Namespace '{namespace}' belongs to another company.")
    sync_defaults = ns_entity.sync_settings
    transcribe_voice = bool(sync_defaults.transcribe_voice_messages) if sync_defaults else False
    speech_to_chat = bool(sync_defaults.speech_to_chat_enabled) if sync_defaults else False
    if body.transcribe_voice_messages is not None:
        transcribe_voice = body.transcribe_voice_messages
    if body.speech_to_chat_enabled is not None:
        speech_to_chat = body.speech_to_chat_enabled

    if body.type == ChannelType.DIRECT:
        direct_member_ids = body.member_ids
        if direct_member_ids is None:
            raise ValueError("direct requires exactly one peer in member_ids.")
        peer_id = direct_member_ids[0]
        existing = await _find_existing_direct_for_pair(
            user_a=actor_user_id,
            user_b=peer_id,
            namespace=namespace,
            company_id=company_id,
            channels=channels,
            channel_access=channel_access,
        )
        if existing is not None:
            read = await _channel_read_for_viewer(
                existing,
                viewer_user_id=actor_user_id,
                company_id=company_id,
                channels=channels,
                channel_access=channel_access,
                user_repository=user_repository,
            )
            return read, False

    channel_id = uuid4().hex
    entity = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        namespace=namespace,
        type=body.type.value,
        name=body.name,
        is_private=body.is_private,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
        pinned_message_ids=[],
        transcribe_voice_messages=transcribe_voice,
        speech_to_chat_enabled=speech_to_chat,
    )
    _ = await channels.create(entity)
    member_ids = list(body.member_ids) if body.member_ids is not None else []
    await channels.ensure_member_row(channel_id, actor_user_id, company_id)
    for member_id in member_ids:
        await channels.ensure_member_row(channel_id, member_id, company_id)
    try:
        await channel_access.sync_channel_created(
            channel_id,
            company_id=company_id,
            owner_user_id=actor_user_id,
            member_user_ids=member_ids,
        )
    except Exception:
        _ = await channels.delete(channel_id)
        raise

    read = await _channel_read_for_viewer(
        entity,
        viewer_user_id=actor_user_id,
        company_id=company_id,
        channels=channels,
        channel_access=channel_access,
        user_repository=user_repository,
    )
    return read, True


async def send_message(
    channel_id: str,
    body: MessageCreate,
    *,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    user_repository: UserRepository | None = None,
    forwarded_from_channel_id: str | None = None,
    forwarded_from_channel_name: str | None = None,
) -> MessageRead:
    message_id = uuid4().hex
    sent_at = datetime.now(tz=UTC)
    row = await messages.create_message(
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
    return await message_read_from_db(row, messages, user_repository)


async def send_message_with_side_effects(
    *,
    channel_id: str,
    body: MessageCreate,
    user: "User",
    container: "SyncContainer",
) -> MessageRead:
    company_id = require_company().company_id
    await _ensure_actor_may_send_to_channel(
        channel_id=channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        body=body,
        authz=container.authz_service,
        calls=container.call_repository,
    )
    normalized_body = await _normalize_message_create_mentions(
        body,
        channel_id=channel_id,
        company_id=company_id,
        actor_user_id=user.user_id,
        channel_access=container.channel_access_service,
    )
    message = await send_message(
        channel_id,
        normalized_body,
        actor_user_id=user.user_id,
        company_id=company_id,
        messages=container.message_repository,
        user_repository=container.user_repository,
    )
    await _enqueue_channel_message_notifications(
        channel_id=channel_id,
        body=normalized_body,
        message=message,
        company_id=company_id,
        actor_user_id=user.user_id,
        channels=container.channel_repository,
        channel_access=container.channel_access_service,
        user_repository=container.user_repository,
    )
    recipients = await channel_recipient_user_ids(
        container.channel_access_service, channel_id
    )
    channel_entity = await container.channel_repository.get(channel_id)
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
                await container.message_repository.replace_message_contents(
                    message.message_id, processing_contents, edited_at
                )
                proc_entity = await container.message_repository.get_by_id_for_company(
                    message.message_id, company_id
                )
                if proc_entity is None:
                    raise WsCommandError(
                        "internal", "Message disappeared after auto-transcription start.",
                              error_code='internal',
                          )
                message = await message_read_from_db(
                    proc_entity, container.message_repository, container.user_repository
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


async def create_thread(
    body: ThreadCreate,
    *,
    actor_user_id: str,
    company_id: str,
    threads: ThreadRepository,
    messages: MessageRepository,
    user_repository: UserRepository | None = None,
) -> ThreadRead:
    root = await messages.get(body.root_message_id)
    if root is None:
        raise ValueError("root_message_id not found.")

    thread_id = uuid4().hex
    entity = SyncThread(
        thread_id=thread_id,
        company_id=company_id,
        channel_id=root.channel_id,
        root_message_id=body.root_message_id,
        title=body.title,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
    )
    _ = await threads.create(entity)
    created_by = await _user_brief(user_repository, actor_user_id)
    return ThreadRead(
        thread_id=thread_id,
        channel_id=root.channel_id,
        root_message_id=body.root_message_id,
        title=body.title,
        created_at=entity.created_at,
        created_by=created_by,
    )


async def upsert_git_resource(
    body: GitResourceRefCreate, *, company_id: str, git_refs: GitResourceRefRepository
) -> GitResourceRefRead:
    ref_id = f"{body.provider.value}:{body.kind.value}:{body.project_key}:{body.external_id}"
    entity = SyncGitResourceRef(
        git_ref_id=ref_id,
        company_id=company_id,
        provider=body.provider.value,
        kind=body.kind.value,
        project_key=body.project_key,
        external_id=body.external_id,
        url=body.url,
        extra=body.extra or {},
    )
    _ = await git_refs.update(entity)
    return GitResourceRefRead(
        git_ref_id=ref_id,
        provider=body.provider,
        kind=body.kind,
        project_key=body.project_key,
        external_id=body.external_id,
        url=body.url,
        extra=body.extra or {},
    )
