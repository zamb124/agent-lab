"""Внутренние helpers Sync.

Это библиотека приватных функций (`_create_channel`, `_send_message`, …),
которыми пользуются `op_*` из `apps/sync/realtime/operations.py`. Никаких
веток `if cmd.type == ...` и никаких `CommandEnvelope` / `execute_command`
здесь нет — единый pipeline команд живёт в `operations.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlparse
from uuid import uuid4

from livekit.api.twirp_client import TwirpError, TwirpErrorCode

from apps.sync.channel_lane_preview import lane_preview_from_content_row
from apps.sync.channel_read_helpers import channel_read_entity_minimal
from apps.sync.db.models import (
    SyncCallRecording,
    SyncChannel,
    SyncGitResourceRef,
    SyncMessage,
    SyncThread,
)
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.meeting_repository import CallRecordingRepository
from apps.sync.db.repositories.thread_repository import ThreadRepository
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.channels import ChannelRead, ChannelType, ChannelUpdate
from apps.sync.models.common import UserBrief
from apps.sync.models.git import GitResourceRefRead
from apps.sync.models.messages import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    CallBoundaryContent,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    MessageRead,
    MessageStatus,
    TextPlainContent,
)
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.threads import ThreadRead
from apps.sync.realtime.notification_tasks import (
    deliver_channel_message_notification,
    deliver_sync_mention_notification,
)
from apps.sync.sender_display import sender_brief_for_message
from core.calls.livekit_client import LiveKitClient
from core.config import get_settings
from core.db.repositories.namespace_repository import NamespaceRepository
from core.db.repositories.user_repository import UserRepository
from core.files.models import VideoAttachmentContent
from core.logging import get_logger
from core.models.identity_models import Namespace

logger = get_logger(__name__)


async def _channel_recipient_user_ids(
    channels: ChannelRepository,
    channel_id: str,
    company_id: str,
) -> list[str]:
    return await channels.list_member_user_ids(channel_id, company_id=company_id)


async def _maybe_start_speech_to_chat_poll(
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
        raise ValueError(f"Канал {channel_id} не найден.")
    if not ch.speech_to_chat_enabled:
        return
    from apps.sync.realtime.tasks import sync_speech_to_chat_poll_task

    await sync_speech_to_chat_poll_task.kiq(call_id=call_id, company_id=company_id)


def _normalize_s3_egress_endpoint(endpoint_url: str | None) -> str | None:
    if endpoint_url is None:
        return None
    trimmed = endpoint_url.strip()
    if trimmed == "":
        return None
    parsed = urlparse(trimmed)
    if parsed.scheme == "":
        return trimmed
    if parsed.netloc == "":
        raise ValueError(f"Некорректный endpoint_url для S3 egress: {endpoint_url}")
    hostname = parsed.hostname
    if hostname is None or hostname == "":
        raise ValueError(f"Некорректный hostname в endpoint_url для S3 egress: {endpoint_url}")
    if hostname == "localhost" or hostname == "127.0.0.1":
        hostname = "host.docker.internal"
    if parsed.port is None:
        netloc = hostname
    else:
        netloc = f"{hostname}:{parsed.port}"
    return f"{parsed.scheme}://{netloc}"


def _build_livekit_recording_client() -> LiveKitClient:
    settings = get_settings()
    return LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )


def _recording_read_from_entity(recording: SyncCallRecording) -> CallRecordingRead:
    return CallRecordingRead(
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


async def _stop_and_finalize_recording(
    *,
    call,
    recording: SyncCallRecording,
    company_id: str,
    actor_user_id: str,
    call_recordings: CallRecordingRepository,
) -> CallRecordingRead:
    if recording.provider_job_id is None or recording.provider_job_id == "":
        raise ValueError(
            f"У записи {recording.recording_id} отсутствует provider_job_id, невозможно остановить egress."
        )
    settings = get_settings()
    if settings.recording_max_duration_seconds <= 0:
        raise ValueError("recording_max_duration_seconds должен быть больше 0.")
    if recording.started_at is not None:
        max_end_at = recording.started_at + timedelta(seconds=settings.recording_max_duration_seconds)
        logger.info(
            "call.recording.stop duration check: call_id=%s recording_id=%s started_at=%s max_end_at=%s now=%s",
            call.call_id,
            recording.recording_id,
            recording.started_at.isoformat(),
            max_end_at.isoformat(),
            datetime.now(UTC).isoformat(),
        )
    livekit_client = _build_livekit_recording_client()
    logger.info(
        "call.recording.stop egress stop: call_id=%s recording_id=%s egress_id=%s",
        call.call_id,
        recording.recording_id,
        recording.provider_job_id,
    )
    try:
        await livekit_client.stop_egress(
            egress_id=recording.provider_job_id,
            company_id=company_id,
            user_id=actor_user_id,
        )
    except TwirpError as exc:
        if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
            logger.warning(
                "call.recording.stop egress already finished: call_id=%s recording_id=%s egress_id=%s code=%s message=%s",
                call.call_id,
                recording.recording_id,
                recording.provider_job_id,
                exc.code,
                str(exc),
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
        raise RuntimeError("Запись пропала после обновления.")
    from apps.sync.realtime.tasks import sync_finalize_recording_task

    await sync_finalize_recording_task.kiq(
        recording_id=updated_recording.recording_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
    )
    return _recording_read_from_entity(updated_recording)


def _notification_preview_from_message(message: MessageRead) -> str:
    ordered = sorted(message.contents, key=lambda c: c.order)
    for c in ordered:
        if c.type == MessageContentType.TEXT_PLAIN:
            return lane_preview_from_content_row(c.type.value, c.data.model_dump())
    if message.contents:
        c0 = sorted(message.contents, key=lambda c: c.order)[0]
        return lane_preview_from_content_row(c0.type.value, c0.data.model_dump())
    return "Новое сообщение"


async def _enqueue_channel_message_notifications(
    *,
    payload,
    message: MessageRead,
    company_id: str,
    actor_user_id: str,
    channels: ChannelRepository,
) -> None:
    entity = await channels.get(payload.channel_id)
    if entity is None:
        raise ValueError(f"Канал {payload.channel_id} не найден.")
    preview = _notification_preview_from_message(message)
    if entity.type == ChannelType.DIRECT.value:
        title = message.sender.display_name
    else:
        title = entity.name or "Канал"
    member_ids = await channels.list_member_user_ids(payload.channel_id, company_id=company_id)
    mentioned: set[str] = set(message.mentioned_user_ids or [])
    is_root_lane = payload.body.thread_id is None

    for uid in member_ids:
        if uid == actor_user_id:
            continue
        if uid in mentioned:
            await deliver_sync_mention_notification.kiq(
                recipient_user_id=uid,
                channel_id=payload.channel_id,
                company_id=company_id,
                message_id=message.id,
                sender_display_name=message.sender.display_name,
                notification_title=title,
                body_preview=preview,
            )
        elif is_root_lane:
            await deliver_channel_message_notification.kiq(
                recipient_user_id=uid,
                channel_id=payload.channel_id,
                company_id=company_id,
                message_id=message.id,
                sender_display_name=message.sender.display_name,
                notification_title=title,
                body_preview=preview,
            )


async def _normalize_message_create_mentions(
    body: MessageCreate,
    *,
    channel_id: str,
    company_id: str,
    actor_user_id: str,
    channels: ChannelRepository,
) -> MessageCreate:
    member_ids = set(
        await channels.list_member_user_ids(channel_id, company_id=company_id)
    )

    def validate_mention_ids(raw: list[str]) -> list[str]:
        ordered = list(dict.fromkeys(raw))
        for uid in ordered:
            if uid not in member_ids:
                raise ValueError(f"Упоминание: пользователь {uid} не участник канала.")
            if uid == actor_user_id:
                raise ValueError("Нельзя упоминать себя.")
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
            raise ValueError("text/plain: ожидается TextPlainContent.")
        new_tp = TextPlainContent(body=d.body, mentions=None)
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
            raise ValueError("text/plain: ожидается TextPlainContent.")
        if d.mentions is None or len(d.mentions) == 0:
            return body
        mids = validate_mention_ids(list(d.mentions))
        new_tp = TextPlainContent(body=d.body, mentions=mids)
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
        raise ValueError("Упоминания требуют текстовый блок text/plain.")
    mids = validate_mention_ids(list(raw_mentions))
    c = body.contents[first_text_idx]
    d = c.data
    if not isinstance(d, TextPlainContent):
        raise ValueError("text/plain: ожидается TextPlainContent.")
    new_tp = TextPlainContent(body=d.body, mentions=mids)
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


def _set_audio_transcription_state(
    contents: list[MessageContentModel],
    *,
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    audio_index = _find_first_audio_content_index(contents)
    if audio_index is None:
        raise ValueError("В сообщении нет аудиоконтента file/audio.")
    next_contents: list[MessageContentModel] = []
    for index, block in enumerate(contents):
        if index != audio_index:
            next_contents.append(block)
            continue
        if not isinstance(block.data, AudioAttachmentContent):
            raise ValueError("file/audio: ожидается AudioAttachmentContent.")
        next_audio = AudioAttachmentContent(
            file_id=block.data.file_id,
            filename=block.data.filename,
            mime_type=block.data.mime_type,
            size=block.data.size,
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


def _set_video_transcription_state(
    contents: list[MessageContentModel],
    *,
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    video_index = _find_first_video_content_index(contents)
    if video_index is None:
        raise ValueError("В сообщении нет видеоконтента file/video.")
    next_contents: list[MessageContentModel] = []
    for index, block in enumerate(contents):
        if index != video_index:
            next_contents.append(block)
            continue
        if not isinstance(block.data, VideoAttachmentContent):
            raise ValueError("file/video: ожидается VideoAttachmentContent.")
        next_video = VideoAttachmentContent(
            file_id=block.data.file_id,
            filename=block.data.filename,
            mime_type=block.data.mime_type,
            size=block.data.size,
            duration_ms=block.data.duration_ms,
            transcription_status=status,
            transcription_text=transcription_text,
            transcription_error=transcription_error,
        )
        next_contents.append(
            MessageContentModel(type=block.type, data=next_video, order=block.order)
        )
    return next_contents


async def _ensure_actor_may_send_to_channel(
    *,
    channel_id: str,
    company_id: str,
    actor_user_id: str,
    body: MessageCreate,
    channels: ChannelRepository,
    calls: CallRepository | None,
) -> None:
    is_member = await channels.is_member(channel_id, actor_user_id, company_id=company_id)
    if is_member:
        if body.call_id is None:
            return
        if calls is None:
            raise RuntimeError("CallRepository обязателен при call_id в сообщении.")
        call = await calls.get_call(body.call_id, company_id)
        if call.channel_id != channel_id:
            raise ValueError("call_id не относится к этому каналу.")
        return
    if not actor_user_id.startswith("guest:"):
        raise PermissionError(f"Пользователь не состоит в канале {channel_id}.")
    if body.call_id is None:
        raise PermissionError("Гостю нужен call_id в сообщении.")
    if calls is None:
        raise RuntimeError("CallRepository обязателен для сообщений гостя.")
    call = await calls.get_call(body.call_id, company_id)
    if call.channel_id != channel_id:
        raise ValueError("call_id не относится к этому каналу.")
    if call.status not in ("ringing", "active"):
        raise PermissionError("Звонок не активен.")
    participants = await calls.list_participants(body.call_id)
    mine = next((p for p in participants if p.user_id == actor_user_id), None)
    if mine is None or mine.status != "joined":
        raise PermissionError("Гость не в этом звонке.")


async def _user_brief(user_repository: Optional[UserRepository], user_id: str) -> UserBrief:
    display_name = user_id
    avatar_url = None
    if user_repository is not None:
        u = await user_repository.get(user_id)
        if u is not None:
            display_name = u.name
            avatar_url = u.avatar_url
    return UserBrief(user_id=user_id, display_name=display_name, avatar_url=avatar_url)


async def _message_read_from_db(
    m: SyncMessage,
    messages: MessageRepository,
    user_repository: Optional[UserRepository],
) -> MessageRead:
    content_rows = await messages.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    sender = await sender_brief_for_message(user_repository, m.sender_user_id)
    return message_read_from_entity(m=m, contents=contents, sender=sender)


def _channel_read_entity(entity: SyncChannel) -> ChannelRead:
    return channel_read_entity_minimal(entity)


async def _update_channel(
    channel_id: str,
    body: ChannelUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    channels: ChannelRepository,
) -> ChannelRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("Нет полей для обновления канала.")
    role = await channels.get_member_role(channel_id, actor_user_id)
    if role is None:
        raise PermissionError(f"Пользователь не состоит в канале {channel_id}.")
    if role not in ("owner", "admin"):
        raise PermissionError("Изменение настроек канала доступно только ролям owner и admin.")
    entity = await channels.get(channel_id)
    if entity is None:
        raise ValueError(f"Канал {channel_id} не найден.")
    if entity.company_id != company_id:
        raise PermissionError("Канал принадлежит другой компании.")
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
    await channels.update(entity)
    return _channel_read_entity(entity)


async def _create_channel(
    body,
    *,
    actor_user_id: str,
    company_id: str,
    channels: ChannelRepository,
    namespaces: NamespaceRepository,
) -> ChannelRead:
    """Создаёт канал, привязанный к платформенному `namespace`.

    Дефолты STT (`transcribe_voice_messages`, `speech_to_chat_enabled`)
    берутся из `Namespace.sync_settings`; на канале можно перекрыть точечно
    через `body.transcribe_voice_messages` / `body.speech_to_chat_enabled`.
    """
    if body.type == ChannelType.TOPIC:
        if body.namespace is None or body.namespace == "":
            raise ValueError("Для topic обязателен namespace.")
        if body.name is None:
            raise ValueError("Для topic обязателен name.")

    if body.type == ChannelType.DIRECT:
        mids = body.member_ids
        if mids is None or len(mids) != 1:
            raise ValueError("Для direct в member_ids должен быть ровно один собеседник.")
        if mids[0] == actor_user_id:
            raise ValueError("Нельзя создать личный канал с самим собой.")

    if body.type == ChannelType.CALENDAR_MEETING:
        if body.name is None or body.name.strip() == "":
            raise ValueError("Для calendar_meeting обязателен name (заголовок встречи).")

    namespace = body.namespace if body.namespace else "default"
    ns_entity = await namespaces.get(namespace)
    if ns_entity is None and namespace == "default":
        ns_entity = Namespace(
            name="default",
            company_id=company_id,
            description="Основное пространство",
            is_default=True,
        )
        await namespaces.set(ns_entity)
    if ns_entity is None:
        raise ValueError(f"Namespace '{namespace}' не найден в платформенном реестре.")
    if ns_entity.company_id != company_id:
        raise PermissionError(f"Namespace '{namespace}' принадлежит другой компании.")
    sync_defaults = ns_entity.sync_settings
    transcribe_voice = bool(sync_defaults.transcribe_voice_messages) if sync_defaults else False
    speech_to_chat = bool(sync_defaults.speech_to_chat_enabled) if sync_defaults else False
    if body.transcribe_voice_messages is not None:
        transcribe_voice = body.transcribe_voice_messages
    if body.speech_to_chat_enabled is not None:
        speech_to_chat = body.speech_to_chat_enabled

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
    await channels.create(entity)
    await channels.add_member_if_missing(channel_id, actor_user_id, "owner", company_id)

    if body.member_ids is not None:
        for member_id in body.member_ids:
            await channels.add_member_if_missing(channel_id, member_id, "member", company_id)

    return _channel_read_entity(entity)


async def _send_message(
    channel_id: str,
    body,
    *,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    user_repository: Optional[UserRepository] = None,
    forwarded_from_channel_id: Optional[str] = None,
    forwarded_from_channel_name: Optional[str] = None,
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
    return await _message_read_from_db(row, messages, user_repository)


async def _create_thread(
    body,
    *,
    actor_user_id: str,
    company_id: str,
    threads: ThreadRepository,
    messages: MessageRepository,
    user_repository: Optional[UserRepository] = None,
) -> ThreadRead:
    root = await messages.get(body.root_message_id)
    if root is None:
        raise ValueError("root_message_id не найден.")

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
    await threads.create(entity)
    created_by = await _user_brief(user_repository, actor_user_id)
    return ThreadRead(
        id=thread_id,
        channel_id=root.channel_id,
        root_message_id=body.root_message_id,
        title=body.title,
        created_at=entity.created_at,
        created_by=created_by,
    )


async def _upsert_git_resource(
    body, *, company_id: str, git_refs: GitResourceRefRepository
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
    await git_refs.update(entity)
    return GitResourceRefRead(
        id=ref_id,
        provider=body.provider,
        kind=body.kind,
        project_key=body.project_key,
        external_id=body.external_id,
        url=body.url,
        extra=body.extra or {},
    )
