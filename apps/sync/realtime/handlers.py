"""Бизнес-обработка realtime команд (исполняется в sync-worker)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Optional
from urllib.parse import urlparse
from uuid import uuid4

from apps.sync.channel_lane_preview import lane_preview_from_content_row
from apps.sync.channel_read_helpers import channel_read_entity_minimal
from apps.sync.db.models import (
    SyncCallRecording,
    SyncChannel,
    SyncGitResourceRef,
    SyncMessage,
    SyncSpace,
    SyncThread,
)
from apps.sync.db.repositories.call_repository import CallRepository
from apps.sync.db.repositories.channel_repository import ChannelRepository
from apps.sync.db.repositories.git_resource_ref_repository import GitResourceRefRepository
from apps.sync.db.repositories.message_repository import MessageRepository
from apps.sync.db.repositories.meeting_repository import CallRecordingRepository
from apps.sync.db.repositories.space_repository import SpaceRepository
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
from apps.sync.models.spaces import SpaceRead, SpaceUpdate
from apps.sync.models.threads import ThreadRead
from apps.sync.realtime.call_handlers import (
    _call_read_from_entities,
    handle_call_accept,
    handle_call_decline,
    handle_call_hangup,
    handle_call_invite,
)
from apps.sync.realtime.commands import (
    CallTransferAdminPayload,
    CallHangupPayload,
    CallRecordingStartPayload,
    CallRecordingStopPayload,
    ChannelsCreatePayload,
    ChannelsMarkReadPayload,
    ChannelsTypingPayload,
    ChannelsUpdatePayload,
    CommandEnvelope,
    GitResourcesUpsertPayload,
    MessagesDeletePayload,
    MessagesEditPayload,
    MessagesForwardPayload,
    MessagesMarkReadPayload,
    MessagesPinPayload,
    MessagesReactPayload,
    MessagesSendPayload,
    MessagesTranscribeAudioPayload,
    MessagesTranscribeCallPayload,
    MessagesTranscribeVideoPayload,
    SpacesCreatePayload,
    SpacesUpdatePayload,
    ThreadsCreatePayload,
)
from apps.sync.realtime.events import (
    MessageStatusChangedPayload,
    RealtimeEvent,
    event_channel_created,
    event_channel_pins_changed,
    event_channel_read_updated,
    event_channel_typing,
    event_call_admin_changed,
    event_call_recording_started,
    event_call_recording_stopped,
    event_git_resource_upserted,
    event_message_created,
    event_message_deleted,
    event_message_reaction_changed,
    event_message_status_changed,
    event_message_updated,
    event_space_created,
    event_thread_created,
)
from apps.sync.realtime.notification_tasks import (
    deliver_channel_message_notification,
    deliver_sync_mention_notification,
)
from apps.sync.sender_display import sender_brief_for_message
from core.calls.livekit_client import LiveKitClient
from core.config import get_settings
from core.files.models import VideoAttachmentContent
from core.db.repositories.user_repository import UserRepository
from core.logging import get_logger
from livekit.api.twirp_client import TwirpError, TwirpErrorCode

logger = get_logger(__name__)


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


class CommandExecutionResult:
    def __init__(self, *, ok: bool, result: object | None, events: list[RealtimeEvent]) -> None:
        self.ok = ok
        self.result = result
        self.events = events


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
        await livekit_client.stop_egress(egress_id=recording.provider_job_id)
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
    payload: MessagesSendPayload,
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
            MessageContentModel(
                type=block.type,
                data=next_audio,
                order=block.order,
            )
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
            MessageContentModel(
                type=block.type,
                data=next_video,
                order=block.order,
            )
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


async def _post_call_boundary_message(
    *,
    channel_id: str,
    call_id: str,
    phase: Literal["started", "ended"],
    sender_user_id: str,
    company_id: str,
    messages: MessageRepository,
    user_repository: Optional[UserRepository],
) -> MessageRead:
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
        messages=messages,
        user_repository=user_repository,
    )


async def execute_command(
    cmd: CommandEnvelope,
    *,
    spaces: SpaceRepository,
    channels: ChannelRepository,
    threads: ThreadRepository,
    messages: MessageRepository,
    git_refs: GitResourceRefRepository,
    user_repository: Optional[UserRepository] = None,
    calls: Optional[CallRepository] = None,
    call_recordings: Optional[CallRecordingRepository] = None,
) -> CommandExecutionResult:
    if cmd.type == "spaces.create":
        payload = SpacesCreatePayload.model_validate(cmd.payload)
        space = await _create_space(payload.body, actor_user_id=cmd.actor_user_id, company_id=cmd.company_id, spaces=spaces)
        return CommandExecutionResult(ok=True, result=space, events=[event_space_created(space)])

    if cmd.type == "spaces.update":
        payload = SpacesUpdatePayload.model_validate(cmd.payload)
        space = await _update_space(
            payload.space_id,
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            spaces=spaces,
        )
        return CommandExecutionResult(ok=True, result=space, events=[])

    if cmd.type == "channels.create":
        payload = ChannelsCreatePayload.model_validate(cmd.payload)
        channel = await _create_channel(
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            channels=channels,
            spaces=spaces,
        )
        return CommandExecutionResult(ok=True, result=channel, events=[event_channel_created(channel)])

    if cmd.type == "channels.update":
        payload = ChannelsUpdatePayload.model_validate(cmd.payload)
        channel = await _update_channel(
            payload.channel_id,
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            channels=channels,
        )
        return CommandExecutionResult(ok=True, result=channel, events=[])

    if cmd.type == "channels.mark_read":
        payload = ChannelsMarkReadPayload.model_validate(cmd.payload)
        if await channels.get_member_role(payload.channel_id, cmd.actor_user_id) is None:
            raise PermissionError(
                f"Пользователь не состоит в канале {payload.channel_id}."
            )
        max_at = await messages.max_root_lane_sent_at(
            payload.channel_id,
            company_id=cmd.company_id,
        )
        read_at = max_at if max_at is not None else datetime.now(UTC)
        await channels.set_member_last_read_at(
            payload.channel_id,
            cmd.actor_user_id,
            read_at,
            company_id=cmd.company_id,
        )
        return CommandExecutionResult(
            ok=True,
            result=None,
            events=[
                event_channel_read_updated(
                    payload.channel_id,
                    cmd.actor_user_id,
                    read_at,
                ),
            ],
        )

    if cmd.type == "channels.typing":
        payload = ChannelsTypingPayload.model_validate(cmd.payload)
        if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
            raise PermissionError(
                f"Пользователь не состоит в канале {payload.channel_id}."
            )
        if payload.thread_id is not None and payload.thread_id != "":
            row = await threads.get(payload.thread_id)
            if row is None:
                raise ValueError(f"Тред {payload.thread_id} не найден.")
            if row.company_id != cmd.company_id:
                raise ValueError("Тред не принадлежит компании.")
            if row.channel_id != payload.channel_id:
                raise ValueError("Тред не принадлежит указанному каналу.")
        if user_repository is None:
            raise ValueError("user_repository обязателен для channels.typing.")
        user_brief = await _user_brief(user_repository, cmd.actor_user_id)
        return CommandExecutionResult(
            ok=True,
            result=None,
            events=[
                event_channel_typing(
                    channel_id=payload.channel_id,
                    thread_id=payload.thread_id if payload.thread_id else None,
                    typing=payload.typing,
                    user=user_brief,
                ),
            ],
        )

    if cmd.type == "threads.create":
        payload = ThreadsCreatePayload.model_validate(cmd.payload)
        thread = await _create_thread(
            payload.body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            threads=threads,
            messages=messages,
            user_repository=user_repository,
        )
        return CommandExecutionResult(ok=True, result=thread, events=[event_thread_created(thread)])

    if cmd.type == "messages.send":
        payload = MessagesSendPayload.model_validate(cmd.payload)
        await _ensure_actor_may_send_to_channel(
            channel_id=payload.channel_id,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
            body=payload.body,
            channels=channels,
            calls=calls,
        )
        normalized_body = await _normalize_message_create_mentions(
            payload.body,
            channel_id=payload.channel_id,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
            channels=channels,
        )
        send_payload = MessagesSendPayload(channel_id=payload.channel_id, body=normalized_body)
        message = await _send_message(
            payload.channel_id,
            normalized_body,
            actor_user_id=cmd.actor_user_id,
            company_id=cmd.company_id,
            messages=messages,
            user_repository=user_repository,
        )
        await _enqueue_channel_message_notifications(
            payload=send_payload,
            message=message,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
            channels=channels,
        )
        evs: list[RealtimeEvent] = [event_message_created(message)]
        channel_entity = await channels.get(payload.channel_id)
        if channel_entity is None:
            raise ValueError(f"Канал {payload.channel_id} не найден.")
        if channel_entity.transcribe_voice_messages:
            audio_idx = _find_first_audio_content_index(normalized_body.contents)
            if audio_idx is not None:
                block = normalized_body.contents[audio_idx]
                if isinstance(block.data, AudioAttachmentContent):
                    if (
                        block.data.transcription_status == AudioTranscriptionStatus.IDLE
                        and not block.data.source_speech_to_chat
                    ):
                        if user_repository is None:
                            raise ValueError("user_repository обязателен для авто-транскрипции.")
                        processing_contents = _set_audio_transcription_state(
                            list(message.contents),
                            status=AudioTranscriptionStatus.PROCESSING,
                            transcription_text=None,
                            transcription_error=None,
                        )
                        edited_at = datetime.now(tz=UTC)
                        await messages.replace_message_contents(message.id, processing_contents, edited_at)
                        proc_entity = await messages.get_by_id_for_company(message.id, cmd.company_id)
                        if proc_entity is None:
                            raise RuntimeError("Сообщение пропало после запуска авто-транскрипции.")
                        message = await _message_read_from_db(proc_entity, messages, user_repository)
                        evs.append(event_message_updated(message))
                        from apps.sync.realtime.tasks import sync_transcribe_audio_message_task

                        await sync_transcribe_audio_message_task.kiq(
                            channel_id=payload.channel_id,
                            message_id=message.id,
                            company_id=cmd.company_id,
                            actor_user_id=cmd.actor_user_id,
                        )
        return CommandExecutionResult(ok=True, result=message, events=evs)

    if cmd.type == "messages.mark_read":
        payload = MessagesMarkReadPayload.model_validate(cmd.payload)
        event = event_message_status_changed(
            payload.channel_id,
            MessageStatusChangedPayload(message_id=payload.message_id, status=MessageStatus.READ),
        )
        return CommandExecutionResult(ok=True, result=None, events=[event])

    if cmd.type == "messages.edit":
        payload = MessagesEditPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_edit(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.delete":
        payload = MessagesDeletePayload.model_validate(cmd.payload)
        evs = await _handle_messages_delete(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels
        )
        return CommandExecutionResult(ok=True, result={"message_id": payload.message_id}, events=evs)

    if cmd.type == "messages.forward":
        payload = MessagesForwardPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_forward(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.react":
        payload = MessagesReactPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_react(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels, user_repository
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.pin":
        payload = MessagesPinPayload.model_validate(cmd.payload)
        out, evs = await _handle_messages_pin(
            payload, cmd.actor_user_id, cmd.company_id, messages, channels
        )
        return CommandExecutionResult(ok=True, result=out, events=evs)

    if cmd.type == "messages.transcribe_audio":
        if user_repository is None:
            raise ValueError("user_repository обязателен.")
        payload = MessagesTranscribeAudioPayload.model_validate(cmd.payload)
        if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
            raise ValueError("Нет доступа к каналу.")
        source_message = await messages.get_by_id_for_company(payload.message_id, cmd.company_id)
        if source_message is None:
            raise ValueError("Сообщение не найдено.")
        if source_message.channel_id != payload.channel_id:
            raise ValueError("Несовпадение канала.")
        if source_message.deleted_at is not None:
            raise ValueError("Сообщение удалено.")
        source_rows = await messages.list_contents(payload.message_id)
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
        await messages.replace_message_contents(payload.message_id, processing_contents, edited_at)
        updated_entity = await messages.get_by_id_for_company(payload.message_id, cmd.company_id)
        if updated_entity is None:
            raise RuntimeError("Сообщение пропало после запуска расшифровки.")
        updated_read = await _message_read_from_db(updated_entity, messages, user_repository)
        from apps.sync.realtime.tasks import sync_transcribe_audio_message_task
        await sync_transcribe_audio_message_task.kiq(
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
        )
        return CommandExecutionResult(
            ok=True,
            result=updated_read,
            events=[event_message_updated(updated_read)],
        )

    if cmd.type == "messages.transcribe_video":
        if user_repository is None:
            raise ValueError("user_repository обязателен.")
        payload = MessagesTranscribeVideoPayload.model_validate(cmd.payload)
        if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
            raise ValueError("Нет доступа к каналу.")
        source_message = await messages.get_by_id_for_company(payload.message_id, cmd.company_id)
        if source_message is None:
            raise ValueError("Сообщение не найдено.")
        if source_message.channel_id != payload.channel_id:
            raise ValueError("Несовпадение канала.")
        if source_message.deleted_at is not None:
            raise ValueError("Сообщение удалено.")
        source_rows = await messages.list_contents(payload.message_id)
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
        await messages.replace_message_contents(payload.message_id, processing_contents, edited_at)
        updated_entity = await messages.get_by_id_for_company(payload.message_id, cmd.company_id)
        if updated_entity is None:
            raise RuntimeError("Сообщение пропало после запуска расшифровки.")
        updated_read = await _message_read_from_db(updated_entity, messages, user_repository)
        from apps.sync.realtime.tasks import sync_transcribe_video_message_task

        await sync_transcribe_video_message_task.kiq(
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
        )
        return CommandExecutionResult(
            ok=True,
            result=updated_read,
            events=[event_message_updated(updated_read)],
        )

    if cmd.type == "messages.transcribe_call":
        if calls is None:
            raise RuntimeError("CallRepository не передан для messages.transcribe_call.")
        payload = MessagesTranscribeCallPayload.model_validate(cmd.payload)
        if not await channels.is_member(payload.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
            raise ValueError("Нет доступа к каналу.")
        call = await calls.get_call(payload.call_id, cmd.company_id)
        if call.channel_id != payload.channel_id:
            raise ValueError("call_id не относится к этому каналу.")
        from apps.sync.realtime.tasks import sync_aggregate_call_transcript_task

        await sync_aggregate_call_transcript_task.kiq(
            channel_id=payload.channel_id,
            call_id=payload.call_id,
            company_id=cmd.company_id,
            actor_user_id=cmd.actor_user_id,
        )
        return CommandExecutionResult(ok=True, result=None, events=[])

    if cmd.type == "git.resources.upsert":
        payload = GitResourcesUpsertPayload.model_validate(cmd.payload)
        ref = await _upsert_git_resource(payload.body, company_id=cmd.company_id, git_refs=git_refs)
        return CommandExecutionResult(ok=True, result=ref, events=[event_git_resource_upserted(ref)])

    if cmd.type in (
        "call.invite",
        "call.accept",
        "call.decline",
        "call.hangup",
        "call.recording.start",
        "call.recording.stop",
        "call.admin.transfer",
    ):
        if calls is None:
            raise RuntimeError("CallRepository не передан в execute_command для call.* команд.")
        if cmd.type in ("call.recording.start", "call.recording.stop", "call.admin.transfer"):
            if call_recordings is None:
                raise RuntimeError("CallRecordingRepository не передан в execute_command для call.* команд.")

        if cmd.type == "call.invite":
            out, evs = await handle_call_invite(
                cmd, calls=calls, channels=channels, user_repository=user_repository
            )
            member_ids = await channels.list_member_user_ids(out.channel_id, company_id=cmd.company_id)
            if user_repository is None:
                raise ValueError("user_repository обязателен для маркера звонка в канале.")
            started_read = await _post_call_boundary_message(
                channel_id=out.channel_id,
                call_id=out.call_id,
                phase="started",
                sender_user_id=out.created_by_user_id,
                company_id=cmd.company_id,
                messages=messages,
                user_repository=user_repository,
            )
            evs.append(event_message_created(started_read))
            if len(member_ids) <= 1:
                now = datetime.now(UTC)
                await calls.update_call_status(out.call_id, "active", started_at=now)
                solo_call = await calls.get_call(out.call_id, cmd.company_id)
                await _maybe_start_speech_to_chat_poll(
                    call_id=solo_call.call_id,
                    company_id=cmd.company_id,
                    channel_id=solo_call.channel_id,
                    livekit_room_name=solo_call.livekit_room_name,
                    channels=channels,
                )
        elif cmd.type == "call.accept":
            out, evs, became_active = await handle_call_accept(cmd, calls=calls)
            if became_active:
                await _maybe_start_speech_to_chat_poll(
                    call_id=out.call_id,
                    company_id=cmd.company_id,
                    channel_id=out.channel_id,
                    livekit_room_name=out.livekit_room_name,
                    channels=channels,
                )
        elif cmd.type == "call.decline":
            out, evs = await handle_call_decline(cmd, calls=calls)
        elif cmd.type == "call.hangup":
            payload = CallHangupPayload.model_validate(cmd.payload)
            auto_stopped_recording_event: RealtimeEvent | None = None
            if call_recordings is not None:
                call = await calls.get_call(payload.call_id, cmd.company_id)
                active_recording = await call_recordings.get_active_for_call(payload.call_id, cmd.company_id)
                if active_recording is not None and active_recording.started_by_user_id == cmd.actor_user_id:
                    stopped_recording = await _stop_and_finalize_recording(
                        call=call,
                        recording=active_recording,
                        company_id=cmd.company_id,
                        actor_user_id=cmd.actor_user_id,
                        call_recordings=call_recordings,
                    )
                    auto_stopped_recording_event = event_call_recording_stopped(stopped_recording)
            out, evs, call_fully_ended = await handle_call_hangup(cmd, calls=calls)
            if auto_stopped_recording_event is not None:
                evs.append(auto_stopped_recording_event)
            if call_fully_ended:
                if user_repository is None:
                    raise ValueError("user_repository обязателен для маркера звонка в канале.")
                boundary_read = await _post_call_boundary_message(
                    channel_id=out.channel_id,
                    call_id=out.call_id,
                    phase="ended",
                    sender_user_id=out.created_by_user_id,
                    company_id=cmd.company_id,
                    messages=messages,
                    user_repository=user_repository,
                )
                evs.append(event_message_created(boundary_read))
        elif cmd.type == "call.recording.start":
            payload = CallRecordingStartPayload.model_validate(cmd.payload)
            call = await calls.get_call(payload.call_id, cmd.company_id)
            if call.status == "ended":
                raise ValueError("Нельзя включить запись завершённого звонка.")
            if call.created_by_user_id != cmd.actor_user_id:
                raise PermissionError("Только админ встречи может включать запись.")
            if call.livekit_room_name is None or call.livekit_room_name == "":
                raise ValueError(f"У звонка {call.call_id} отсутствует livekit_room_name.")
            if not await channels.is_member(call.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
                raise PermissionError("Нет доступа к звонку.")
            active = await call_recordings.get_active_for_call(payload.call_id, cmd.company_id)
            if active is not None:
                raise ValueError("Запись уже запущена.")

            channel_entity = await channels.get(call.channel_id)
            if channel_entity is None:
                raise ValueError(f"Канал {call.channel_id} не найден.")
            settings = get_settings()
            if settings.recording_max_duration_seconds <= 0:
                raise ValueError("recording_max_duration_seconds должен быть больше 0.")
            if not settings.s3.enabled:
                raise ValueError("S3 отключен: запись звонка в S3 недоступна.")
            default_bucket_key = settings.s3.default_bucket
            if default_bucket_key == "":
                raise ValueError("s3.default_bucket не настроен.")
            if default_bucket_key not in settings.s3.buckets:
                raise ValueError(f"Конфиг S3 bucket '{default_bucket_key}' не найден.")
            bucket_config = settings.s3.buckets[default_bucket_key]
            if not bucket_config.enabled:
                raise ValueError(f"S3 bucket '{default_bucket_key}' выключен.")
            if not bucket_config.access_key_id:
                raise ValueError(f"S3 access_key_id не настроен для bucket '{default_bucket_key}'.")
            if not bucket_config.secret_access_key:
                raise ValueError(f"S3 secret_access_key не настроен для bucket '{default_bucket_key}'.")
            if not bucket_config.region_name:
                raise ValueError(f"S3 region_name не настроен для bucket '{default_bucket_key}'.")
            real_bucket_name = bucket_config.bucket_name or default_bucket_key
            if real_bucket_name == "":
                raise ValueError("Имя S3 bucket для egress не может быть пустым.")
            recording_id = uuid4().hex
            egress_filepath = (
                f"sync-recordings/{cmd.company_id}/{call.call_id}/{recording_id}.mp4"
            )
            livekit_client = _build_livekit_recording_client()
            logger.info(
                "call.recording.start egress start: call_id=%s room=%s recording_id=%s filepath=%s bucket=%s",
                call.call_id,
                call.livekit_room_name,
                recording_id,
                egress_filepath,
                real_bucket_name,
            )
            await livekit_client.create_room(call.livekit_room_name)
            egress_info = await livekit_client.start_room_composite_egress_to_s3(
                room_name=call.livekit_room_name,
                filepath=egress_filepath,
                s3_access_key=bucket_config.access_key_id,
                s3_secret_key=bucket_config.secret_access_key,
                s3_region=bucket_config.region_name,
                s3_bucket=real_bucket_name,
                s3_endpoint=_normalize_s3_egress_endpoint(bucket_config.endpoint_url),
                audio_only=(call.call_type == "audio"),
            )
            provider_job_id = getattr(egress_info, "egress_id", None)
            if not isinstance(provider_job_id, str) or provider_job_id == "":
                raise RuntimeError("LiveKit не вернул egress_id после старта записи.")
            logger.info(
                "call.recording.start egress started: call_id=%s recording_id=%s egress_id=%s",
                call.call_id,
                recording_id,
                provider_job_id,
            )
            recording = SyncCallRecording(
                recording_id=recording_id,
                call_id=call.call_id,
                company_id=cmd.company_id,
                channel_id=call.channel_id,
                space_id=channel_entity.space_id,
                status="recording",
                started_by_user_id=cmd.actor_user_id,
                provider_job_id=provider_job_id,
                started_at=datetime.now(UTC),
            )
            await call_recordings.create(recording)
            out = _recording_read_from_entity(recording)
            evs = [event_call_recording_started(out)]
        elif cmd.type == "call.recording.stop":
            payload = CallRecordingStopPayload.model_validate(cmd.payload)
            call = await calls.get_call(payload.call_id, cmd.company_id)
            if not await channels.is_member(call.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
                raise PermissionError("Нет доступа к звонку.")
            active = await call_recordings.get_active_for_call(payload.call_id, cmd.company_id)
            if active is None:
                raise ValueError("Активная запись не найдена.")
            is_meeting_admin = call.created_by_user_id == cmd.actor_user_id
            is_recording_starter = active.started_by_user_id == cmd.actor_user_id
            if not is_meeting_admin and not is_recording_starter:
                raise PermissionError(
                    "Останавливать запись может только админ встречи или пользователь, который её запустил."
                )
            out = await _stop_and_finalize_recording(
                call=call,
                recording=active,
                company_id=cmd.company_id,
                actor_user_id=cmd.actor_user_id,
                call_recordings=call_recordings,
            )
            evs = [event_call_recording_stopped(out)]
        elif cmd.type == "call.admin.transfer":
            payload = CallTransferAdminPayload.model_validate(cmd.payload)
            call = await calls.get_call(payload.call_id, cmd.company_id)
            if call.created_by_user_id != cmd.actor_user_id:
                raise PermissionError("Только текущий админ встречи может передавать админку.")
            if not await channels.is_member(call.channel_id, cmd.actor_user_id, company_id=cmd.company_id):
                raise PermissionError("Нет доступа к звонку.")
            if not await channels.is_member(call.channel_id, payload.target_user_id, company_id=cmd.company_id):
                raise ValueError("Новый админ не является участником канала.")
            if payload.target_user_id.startswith("guest:"):
                raise ValueError("Нельзя назначить гостя админом встречи.")
            participants = await calls.list_participants(call.call_id)
            target_participant = next((item for item in participants if item.user_id == payload.target_user_id), None)
            if target_participant is None:
                raise ValueError("Новый админ не найден среди участников звонка.")
            if target_participant.status != "joined":
                raise ValueError("Новый админ должен быть активным участником звонка.")
            await calls.set_call_admin(call.call_id, payload.target_user_id)
            updated_call = await calls.get_call(call.call_id, cmd.company_id)
            updated_participants = await calls.list_participants(call.call_id)
            out = _call_read_from_entities(updated_call, updated_participants)
            evs = [event_call_admin_changed(out)]
        else:
            raise RuntimeError(f"Неизвестный call.* тип команды: {cmd.type!r}.")
        return CommandExecutionResult(ok=True, result=out, events=evs)

    raise RuntimeError(f"Неизвестный тип команды: {cmd.type!r}.")


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


def _recording_read_from_entity(recording) -> CallRecordingRead:
    return CallRecordingRead(
        recording_id=recording.recording_id,
        call_id=recording.call_id,
        channel_id=recording.channel_id,
        space_id=recording.space_id,
        started_by_user_id=recording.started_by_user_id,
        status=recording.status,
        provider_job_id=recording.provider_job_id,
        raw_file_id=recording.raw_file_id,
        started_at=recording.started_at,
        ended_at=recording.ended_at,
        created_at=recording.created_at,
        error=recording.error,
    )


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
        {
            "user_id": actor_user_id,
            "emoji": emoji,
            "created_at": now.isoformat(),
        }
    )
    return filtered


async def _create_space(body, *, actor_user_id: str, company_id: str, spaces: SpaceRepository) -> SpaceRead:
    space_id = uuid4().hex
    entity = SyncSpace(
        space_id=space_id,
        company_id=company_id,
        name=body.name,
        description=body.description,
        created_at=datetime.now(tz=UTC),
        created_by_user_id=actor_user_id,
        transcribe_voice_messages=body.transcribe_voice_messages,
        speech_to_chat_enabled=body.speech_to_chat_enabled,
    )
    await spaces.create(entity)
    return SpaceRead(
        id=space_id,
        name=entity.name,
        description=entity.description,
        avatar_url=entity.avatar_url,
        namespace=entity.namespace,
        created_at=entity.created_at,
        created_by_user_id=actor_user_id,
        transcribe_voice_messages=entity.transcribe_voice_messages,
        speech_to_chat_enabled=entity.speech_to_chat_enabled,
    )


async def _update_space(
    space_id: str,
    body: SpaceUpdate,
    *,
    actor_user_id: str,
    company_id: str,
    spaces: SpaceRepository,
) -> SpaceRead:
    data = body.model_dump(exclude_unset=True)
    if not data:
        raise ValueError("Нет полей для обновления пространства.")
    entity = await spaces.get(space_id)
    if entity is None:
        raise ValueError(f"Пространство {space_id} не найдено.")
    if entity.company_id != company_id:
        raise PermissionError("Пространство принадлежит другой компании.")
    if "name" in data:
        entity.name = data["name"]
    if "description" in data:
        entity.description = data["description"]
    if "avatar_url" in data:
        entity.avatar_url = data["avatar_url"]
    if "namespace" in data:
        entity.namespace = data["namespace"]
    if "transcribe_voice_messages" in data:
        entity.transcribe_voice_messages = data["transcribe_voice_messages"]
    if "speech_to_chat_enabled" in data:
        entity.speech_to_chat_enabled = data["speech_to_chat_enabled"]
    await spaces.update(entity)
    return SpaceRead(
        id=entity.space_id,
        name=entity.name,
        description=entity.description,
        avatar_url=entity.avatar_url,
        namespace=entity.namespace,
        created_at=entity.created_at,
        created_by_user_id=entity.created_by_user_id,
        transcribe_voice_messages=entity.transcribe_voice_messages,
        speech_to_chat_enabled=entity.speech_to_chat_enabled,
    )


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
    spaces: SpaceRepository,
) -> ChannelRead:
    if body.type == ChannelType.TOPIC:
        if body.space_id is None:
            raise ValueError("Для topic обязателен space_id.")
        if body.name is None:
            raise ValueError("Для topic обязателен name.")

    if body.type == ChannelType.DIRECT:
        if body.space_id is not None:
            raise ValueError("Для direct не задают space_id.")
        mids = body.member_ids
        if mids is None or len(mids) != 1:
            raise ValueError("Для direct в member_ids должен быть ровно один собеседник.")
        if mids[0] == actor_user_id:
            raise ValueError("Нельзя создать личный канал с самим собой.")

    if body.type == ChannelType.CALENDAR_MEETING:
        if body.name is None or body.name.strip() == "":
            raise ValueError("Для calendar_meeting обязателен name (заголовок встречи).")

    transcribe_voice = False
    speech_to_chat = False
    if body.space_id is not None:
        space_ent = await spaces.get(body.space_id)
        if space_ent is None:
            raise ValueError(f"Пространство {body.space_id} не найдено.")
        if space_ent.company_id != company_id:
            raise PermissionError("Пространство принадлежит другой компании.")
        transcribe_voice = space_ent.transcribe_voice_messages
        speech_to_chat = space_ent.speech_to_chat_enabled
    if body.transcribe_voice_messages is not None:
        transcribe_voice = body.transcribe_voice_messages
    if body.speech_to_chat_enabled is not None:
        speech_to_chat = body.speech_to_chat_enabled

    channel_id = uuid4().hex
    entity = SyncChannel(
        channel_id=channel_id,
        company_id=company_id,
        space_id=body.space_id,
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


async def _upsert_git_resource(body, *, company_id: str, git_refs: GitResourceRefRepository) -> GitResourceRefRead:
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


async def _handle_messages_edit(
    payload: MessagesEditPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if user_repository is None:
        raise ValueError("user_repository обязателен.")
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Сообщение удалено.")
    if m.sender_user_id != actor_user_id:
        raise ValueError("Редактировать может только автор.")
    edited_at = datetime.now(tz=UTC)
    await messages.replace_message_contents(payload.message_id, payload.body.contents, edited_at)
    m2 = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise RuntimeError("Сообщение пропало после редактирования.")
    read = await _message_read_from_db(m2, messages, user_repository)
    return read, [event_message_updated(read)]


async def _handle_messages_delete(
    payload: MessagesDeletePayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
) -> list[RealtimeEvent]:
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    role = await channels.get_member_role(payload.channel_id, actor_user_id)
    if role is None:
        raise ValueError("Нет доступа к каналу.")
    if m.sender_user_id != actor_user_id and role != "owner":
        raise ValueError("Недостаточно прав на удаление.")
    now = datetime.now(tz=UTC)
    await messages.soft_delete_message(payload.message_id, now)
    ch = await channels.get(payload.channel_id)
    evs: list[RealtimeEvent] = [event_message_deleted(payload.channel_id, payload.message_id)]
    if ch is not None:
        pids = list(ch.pinned_message_ids or []) if isinstance(ch.pinned_message_ids, list) else []
        if payload.message_id in pids:
            new_pids = [x for x in pids if x != payload.message_id]
            await channels.set_pinned_message_ids(payload.channel_id, new_pids, company_id=company_id)
            ch2 = await channels.get(payload.channel_id)
            if ch2 is not None:
                evs.append(event_channel_pins_changed(_channel_read_entity(ch2)))
    return evs


async def _handle_messages_forward(
    payload: MessagesForwardPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if not await channels.is_member(payload.from_channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к исходному каналу.")
    if not await channels.is_member(payload.to_channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к целевому каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.from_channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Нельзя переслать удалённое сообщение.")
    content_rows = await messages.list_contents(m.message_id)
    contents: list[MessageContentModel] = []
    for row in content_rows:
        contents.append(
            MessageContentModel.model_validate(
                {"type": row.type, "data": row.data, "order": row.order}
            )
        )
    body = MessageCreate(
        thread_id=payload.thread_id,
        parent_message_id=None,
        contents=contents,
    )
    src_ch = await channels.get(payload.from_channel_id)
    if src_ch is None:
        raise ValueError("Исходный канал не найден.")
    raw_name = src_ch.name
    fwd_label = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() != "" else None
    new_read = await _send_message(
        payload.to_channel_id,
        body,
        actor_user_id=actor_user_id,
        company_id=company_id,
        messages=messages,
        user_repository=user_repository,
        forwarded_from_channel_id=payload.from_channel_id,
        forwarded_from_channel_name=fwd_label,
    )
    return new_read, [event_message_created(new_read)]


async def _handle_messages_react(
    payload: MessagesReactPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
    user_repository: Optional[UserRepository],
) -> tuple[MessageRead, list[RealtimeEvent]]:
    if user_repository is None:
        raise ValueError("user_repository обязателен.")
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Сообщение удалено.")
    now = datetime.now(tz=UTC)
    new_reactions = _apply_reaction_json(m.reactions, actor_user_id, payload.emoji, now)
    await messages.set_message_reactions(payload.message_id, new_reactions)
    m2 = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m2 is None:
        raise RuntimeError("Сообщение пропало после реакции.")
    read = await _message_read_from_db(m2, messages, user_repository)
    return read, [
        event_message_reaction_changed(payload.channel_id, payload.message_id, new_reactions),
        event_message_updated(read),
    ]


async def _handle_messages_pin(
    payload: MessagesPinPayload,
    actor_user_id: str,
    company_id: str,
    messages: MessageRepository,
    channels: ChannelRepository,
) -> tuple[ChannelRead, list[RealtimeEvent]]:
    if not await channels.is_member(payload.channel_id, actor_user_id, company_id=company_id):
        raise ValueError("Нет доступа к каналу.")
    role = await channels.get_member_role(payload.channel_id, actor_user_id)
    if role != "owner":
        raise ValueError("Закреплять может только владелец канала.")
    m = await messages.get_by_id_for_company(payload.message_id, company_id)
    if m is None:
        raise ValueError("Сообщение не найдено.")
    if m.channel_id != payload.channel_id:
        raise ValueError("Несовпадение канала.")
    if m.deleted_at is not None:
        raise ValueError("Нельзя закрепить удалённое сообщение.")
    ch = await channels.get(payload.channel_id)
    if ch is None:
        raise ValueError("Канал не найден.")
    pids = list(ch.pinned_message_ids or []) if isinstance(ch.pinned_message_ids, list) else []
    if payload.action == "add":
        if payload.message_id not in pids:
            pids.insert(0, payload.message_id)
    else:
        pids = [x for x in pids if x != payload.message_id]
    await channels.set_pinned_message_ids(payload.channel_id, pids, company_id=company_id)
    ch2 = await channels.get(payload.channel_id)
    if ch2 is None:
        raise RuntimeError("Канал пропал после обновления.")
    cr = _channel_read_entity(ch2)
    return cr, [event_channel_pins_changed(cr)]
