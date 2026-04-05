"""TaskIQ задачи realtime слоя Sync."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import redis.asyncio as redis_async

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncCallRecording, SyncFile
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.models.meetings import CallRecordingRead
from apps.sync.models.messages import (
    SYNC_MESSAGE_TEXT_MAX_CHARS,
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    MessageContentModel,
    MessageContentType,
    MessageCreate,
    TextPlainContent,
)
from apps.sync.realtime.broker import broker
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope, MessagesSendPayload
from apps.sync.realtime.events import event_call_recording_failed, event_message_updated
from apps.sync.realtime.publish_events import publish_realtime_events
from apps.sync.sender_display import sender_brief_for_message
from core.calls.livekit_client import LiveKitClient
from core.clients.stt_client import STTClientFactory
from core.config import get_settings
from core.files.models import VideoAttachmentContent
from core.http import get_httpx_client
from core.logging import get_logger
from core.models.billing_models import UsageType
from core.tracing import attributes as trace_attributes
from core.tracing.operation_span import traced_operation
from core.utils.tokens import get_token_service

logger = get_logger(__name__)


_TRANSCRIBE_AUDIO_LOCK_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""


def _normalize_mime_type(raw_mime_type: str | None) -> str | None:
    if raw_mime_type is None:
        return None
    if raw_mime_type == "":
        return None
    return raw_mime_type.split(";", 1)[0].strip().lower()


def _validate_stt_result_text(
    *,
    transcript_result: Any,
    job_id: str,
    context: str,
) -> str:
    if transcript_result.status != AudioTranscriptionStatus.DONE:
        raise ValueError(
            "STT вернул неуспешный статус транскрипции "
            f"для job_id={job_id}: {transcript_result.status.value}. context={context}"
        )
    transcript_text = transcript_result.text
    if transcript_text.strip() == "":
        raise ValueError(f"STT вернул пустую транскрипцию для job_id={job_id}. context={context}")
    return transcript_text


def _is_stt_format_not_recognized_error(error: Exception) -> bool:
    message = str(error).lower()
    return (
        "format not recognised" in message
        or "format not recognized" in message
        or "error opening <_io.bytesio object>" in message
    )


def _audio_input_extension(file_name: str, mime_type: str) -> str:
    if file_name == "":
        raise ValueError("file_name не может быть пустым.")
    if mime_type == "":
        raise ValueError("mime_type не может быть пустым.")
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix != "":
        return suffix
    normalized_mime_type = _normalize_mime_type(mime_type)
    if normalized_mime_type is None:
        return "bin"
    if "/" not in normalized_mime_type:
        return "bin"
    subtype = normalized_mime_type.split("/", 1)[1]
    subtype_map = {
        "x-m4a": "m4a",
        "mpeg": "mp3",
    }
    return subtype_map.get(subtype, subtype)


def _split_audio_for_stt_chunks(
    *,
    audio_bytes: bytes,
    file_name: str,
    mime_type: str,
    max_upload_bytes: int,
    chunk_duration_seconds: int,
    chunk_bitrate_kbps: int,
    chunk_sample_rate_hz: int,
    chunk_channels: int,
) -> list[tuple[str, bytes, str]]:
    if not audio_bytes:
        raise ValueError("audio_bytes не может быть пустым.")
    if max_upload_bytes <= 0:
        raise ValueError("max_upload_bytes должен быть больше 0.")
    if chunk_duration_seconds <= 0:
        raise ValueError("chunk_duration_seconds должен быть больше 0.")
    if chunk_bitrate_kbps <= 0:
        raise ValueError("chunk_bitrate_kbps должен быть больше 0.")
    if chunk_sample_rate_hz <= 0:
        raise ValueError("chunk_sample_rate_hz должен быть больше 0.")
    if chunk_channels <= 0:
        raise ValueError("chunk_channels должен быть больше 0.")
    input_extension = _audio_input_extension(file_name=file_name, mime_type=mime_type)
    file_stem = Path(file_name).stem
    if file_stem == "":
        file_stem = "recording"
    chunks: list[tuple[str, bytes, str]] = []
    with tempfile.TemporaryDirectory(prefix="sync-stt-chunks-") as work_dir:
        source_path = Path(work_dir) / f"source.{input_extension}"
        source_path.write_bytes(audio_bytes)
        segment_pattern = Path(work_dir) / "segment-%04d.mp3"
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            str(chunk_channels),
            "-ar",
            str(chunk_sample_rate_hz),
            "-b:a",
            f"{chunk_bitrate_kbps}k",
            "-f",
            "segment",
            "-segment_time",
            str(chunk_duration_seconds),
            "-reset_timestamps",
            "1",
            str(segment_pattern),
        ]
        ffmpeg_result = subprocess.run(
            ffmpeg_cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if ffmpeg_result.returncode != 0:
            stderr = ffmpeg_result.stderr.strip()
            raise RuntimeError(
                "Не удалось подготовить аудио чанки для STT через ffmpeg. "
                f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
        segment_files = sorted(Path(work_dir).glob("segment-*.mp3"))
        if len(segment_files) == 0:
            raise RuntimeError("ffmpeg не сформировал ни одного STT чанка.")
        for chunk_index, segment_file in enumerate(segment_files, start=1):
            chunk_bytes = segment_file.read_bytes()
            if len(chunk_bytes) == 0:
                raise ValueError(f"STT chunk #{chunk_index} получился пустым.")
            if len(chunk_bytes) > max_upload_bytes:
                raise ValueError(
                    "STT chunk превышает допустимый размер upload. "
                    f"chunk_index={chunk_index} size={len(chunk_bytes)} max={max_upload_bytes}. "
                    "Уменьшите stt.cloud_ru.chunk_duration_seconds или chunk_bitrate_kbps."
                )
            chunk_file_name = f"{file_stem}-part-{chunk_index:04d}.mp3"
            chunks.append((chunk_file_name, chunk_bytes, "audio/mpeg"))
    if len(chunks) == 0:
        raise ValueError("Не удалось сформировать чанки для STT.")
    return chunks


async def _transcribe_audio_with_chunking(
    *,
    job_id: str,
    audio_bytes: bytes,
    file_name: str,
    mime_type: str,
    language: str,
) -> str:
    settings = get_settings()
    cloud_config = settings.stt.cloud_ru
    max_upload_bytes = cloud_config.max_upload_bytes
    chunk_duration_seconds = cloud_config.chunk_duration_seconds
    chunk_bitrate_kbps = cloud_config.chunk_bitrate_kbps
    chunk_sample_rate_hz = cloud_config.chunk_sample_rate_hz
    chunk_channels = cloud_config.chunk_channels
    stt_client = STTClientFactory.create_client()

    should_chunk_first = len(audio_bytes) > max_upload_bytes
    if not should_chunk_first:
        try:
            transcript_result = await stt_client.transcribe_audio(
                audio_bytes=audio_bytes,
                file_name=file_name,
                mime_type=mime_type,
                language=language,
            )
            return _validate_stt_result_text(
                transcript_result=transcript_result,
                job_id=job_id,
                context="single_request",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 413:
                raise
            logger.warning(
                "STT single request returned 413; switching to chunked mode: job_id=%s file=%s bytes=%s",
                job_id,
                file_name,
                len(audio_bytes),
            )
        except ValueError as exc:
            if not _is_stt_format_not_recognized_error(exc):
                raise
            logger.warning(
                "STT single request returned format error; switching to chunked mode: job_id=%s file=%s mime=%s error=%s",
                job_id,
                file_name,
                mime_type,
                str(exc),
            )

    chunks = _split_audio_for_stt_chunks(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        max_upload_bytes=max_upload_bytes,
        chunk_duration_seconds=chunk_duration_seconds,
        chunk_bitrate_kbps=chunk_bitrate_kbps,
        chunk_sample_rate_hz=chunk_sample_rate_hz,
        chunk_channels=chunk_channels,
    )
    chunk_texts: list[str] = []
    for index, (chunk_file_name, chunk_bytes, chunk_mime_type) in enumerate(chunks, start=1):
        transcript_result = await stt_client.transcribe_audio(
            audio_bytes=chunk_bytes,
            file_name=chunk_file_name,
            mime_type=chunk_mime_type,
            language=language,
        )
        chunk_text = _validate_stt_result_text(
            transcript_result=transcript_result,
            job_id=job_id,
            context=f"chunk_{index}",
        ).strip()
        if chunk_text != "":
            chunk_texts.append(chunk_text)
    if len(chunk_texts) == 0:
        raise ValueError(f"STT вернул пустые транскрипции для всех чанков job_id={job_id}.")
    return "\n".join(chunk_texts)


def _sync_call_aggregate_empty_body() -> str:
    """Текст сообщения в ленте, если нечего агрегировать (строка из core/i18n/translations/ru/sync.json)."""
    path = Path(__file__).resolve().parents[3] / "core" / "i18n" / "translations" / "ru" / "sync.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    key = "call_aggregate_empty_body"
    text = data.get(key)
    if not isinstance(text, str) or text.strip() == "":
        raise ValueError(f"i18n ru/sync.json: обязательный корневой ключ {key!r}.")
    return text.strip()


def _build_interservice_auth_headers(actor_user_id: str, company_id: str) -> dict[str, str]:
    """Authorization + компания. Без X-User-Id: в httpx заголовки — latin-1, guest id может содержать Unicode."""
    token = get_token_service().create_token(actor_user_id, company_id=company_id)
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
    }


def _normalize_http_base_url(url: str) -> str:
    if not isinstance(url, str) or url == "":
        raise ValueError("URL источника записи обязателен.")
    if url.startswith("ws://"):
        return "http://" + url[len("ws://") :]
    if url.startswith("wss://"):
        return "https://" + url[len("wss://") :]
    if url.startswith("http://") or url.startswith("https://"):
        return url
    raise ValueError(f"Неподдерживаемая схема URL источника записи: {url}")


def _extract_egress_file_location(egress_info: Any) -> str | None:
    file_results = getattr(egress_info, "file_results", None)
    if file_results is not None:
        for file_info in file_results:
            location = getattr(file_info, "location", None)
            if isinstance(location, str) and location != "":
                return location
    single_file = getattr(egress_info, "file", None)
    if single_file is not None:
        location = getattr(single_file, "location", None)
        if isinstance(location, str) and location != "":
            return location
    return None


def _egress_sort_key(egress_info: Any) -> tuple[int, int, int]:
    updated_at = int(getattr(egress_info, "updated_at", 0) or 0)
    ended_at = int(getattr(egress_info, "ended_at", 0) or 0)
    started_at = int(getattr(egress_info, "started_at", 0) or 0)
    return updated_at, ended_at, started_at


def _normalize_storage_url_for_worker(*, storage_url: str, testing: bool) -> str:
    if not testing:
        return storage_url
    parsed = urlparse(storage_url)
    if parsed.hostname != "host.docker.internal":
        return storage_url
    if parsed.port is None:
        netloc = "localhost"
    else:
        netloc = f"localhost:{parsed.port}"
    if parsed.scheme == "":
        raise ValueError(f"Некорректный storage_url без схемы: {storage_url}")
    return f"{parsed.scheme}://{netloc}{parsed.path}"


async def _resolve_livekit_egress_result(
    *, room_name: str, timeout_seconds: float, expected_egress_id: str | None = None
) -> tuple[str, str]:
    if room_name == "":
        raise ValueError("livekit room_name обязателен для поиска egress результата.")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds должен быть больше 0.")
    if expected_egress_id is not None and expected_egress_id == "":
        raise ValueError("expected_egress_id не может быть пустой строкой.")

    settings = get_settings()
    wait_timeout_seconds = float(timeout_seconds)
    poll_interval_seconds = settings.calls.finalize_recording_egress_poll_interval_seconds
    elapsed_seconds = 0.0
    last_observed = "none"
    livekit_client = LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )
    logger.info(
        "resolve_egress_result start: room=%s expected_egress_id=%s timeout=%.1fs",
        room_name,
        expected_egress_id,
        wait_timeout_seconds,
    )

    while True:
        logger.info(
            "resolve_egress_result poll: room=%s elapsed=%.1fs",
            room_name,
            elapsed_seconds,
        )
        egress_items = await livekit_client.list_egress(room_name=room_name, active=None)
        logger.info(
            "resolve_egress_result list_egress: room=%s items=%s",
            room_name,
            len(egress_items),
        )
        if len(egress_items) > 0:
            sorted_items = sorted(egress_items, key=_egress_sort_key, reverse=True)
            observed_items: list[str] = []
            for item in sorted_items:
                egress_id = getattr(item, "egress_id", None)
                if expected_egress_id is not None and egress_id != expected_egress_id:
                    continue
                status = getattr(item, "status", None)
                location = _extract_egress_file_location(item)
                ended_at = int(getattr(item, "ended_at", 0) or 0)
                error = getattr(item, "error", None)
                observed_items.append(
                    "id="
                    f"{egress_id or 'unknown'},"
                    f"status={status},"
                    f"ended_at={ended_at},"
                    f"location={'yes' if location else 'no'},"
                    f"error={error}"
                )
                logger.info(
                    "resolve_egress_result matched item: room=%s egress_id=%s status=%s ended_at=%s location=%s error=%s",
                    room_name,
                    egress_id,
                    status,
                    ended_at,
                    "yes" if location else "no",
                    error,
                )
                if location is not None:
                    if not isinstance(egress_id, str) or egress_id == "":
                        raise ValueError(
                            f"LiveKit вернул egress без egress_id для room={room_name}."
                        )
                    logger.info(
                        "resolve_egress_result done: room=%s egress_id=%s location=%s",
                        room_name,
                        egress_id,
                        location,
                    )
                    return egress_id, location
                if ended_at > 0:
                    raise RuntimeError(
                        "LiveKit egress завершился без location. "
                        f"room_name={room_name}, egress_id={egress_id}, status={status}, error={error}."
                    )
            last_observed = "; ".join(observed_items) if observed_items else "none"

        if elapsed_seconds >= wait_timeout_seconds:
            break
        await asyncio.sleep(poll_interval_seconds)
        elapsed_seconds += poll_interval_seconds

    raise RuntimeError(
        "LiveKit egress не вернул готовый файл записи. "
        f"room_name={room_name}, observed={last_observed}. "
        "Проверьте egress service и output конфигурацию."
    )


def _recording_read_from_entity(recording: SyncCallRecording) -> CallRecordingRead:
    return CallRecordingRead(
        recording_id=recording.recording_id,
        call_id=recording.call_id,
        channel_id=recording.channel_id,
        space_id=recording.space_id,
        started_by_user_id=recording.started_by_user_id,
        status=recording.status,  # type: ignore[arg-type]
        provider_job_id=recording.provider_job_id,
        raw_file_id=recording.raw_file_id,
        raw_file_storage_url=None,
        raw_file_download_url=None,
        started_at=recording.started_at,
        ended_at=recording.ended_at,
        created_at=recording.created_at,
        error=recording.error,
    )


async def _load_message_read(container: Any, *, message_id: str, company_id: str) -> Any:
    message_entity = await container.message_repository.get_by_id_for_company(message_id, company_id)
    if message_entity is None:
        raise ValueError(f"Сообщение {message_id} не найдено.")
    rows = await container.message_repository.list_contents(message_id)
    contents = [
        MessageContentModel.model_validate({"type": row.type, "data": row.data, "order": row.order})
        for row in rows
    ]
    sender = await sender_brief_for_message(container.user_repository, message_entity.sender_user_id)
    return message_read_from_entity(m=message_entity, contents=contents, sender=sender)


def _replace_audio_transcription(
    *,
    contents: list[MessageContentModel],
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    replaced = False
    next_contents: list[MessageContentModel] = []
    for block in contents:
        if block.type != MessageContentType.FILE_AUDIO:
            next_contents.append(block)
            continue
        if replaced:
            next_contents.append(block)
            continue
        if not isinstance(block.data, AudioAttachmentContent):
            raise ValueError("file/audio: ожидается AudioAttachmentContent.")
        next_contents.append(
            MessageContentModel(
                type=block.type,
                data=AudioAttachmentContent(
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
                ),
                order=block.order,
            )
        )
        replaced = True
    if not replaced:
        raise ValueError("Сообщение не содержит file/audio.")
    return next_contents


def _extract_audio_info(contents: list[MessageContentModel]) -> AudioAttachmentContent:
    ordered = sorted(contents, key=lambda item: item.order)
    for block in ordered:
        if block.type != MessageContentType.FILE_AUDIO:
            continue
        if not isinstance(block.data, AudioAttachmentContent):
            raise ValueError("file/audio: ожидается AudioAttachmentContent.")
        return block.data
    raise ValueError("Сообщение не содержит file/audio.")


def _replace_video_transcription(
    *,
    contents: list[MessageContentModel],
    status: AudioTranscriptionStatus,
    transcription_text: str | None,
    transcription_error: str | None,
) -> list[MessageContentModel]:
    replaced = False
    next_contents: list[MessageContentModel] = []
    for block in contents:
        if block.type != MessageContentType.FILE_VIDEO:
            next_contents.append(block)
            continue
        if replaced:
            next_contents.append(block)
            continue
        if not isinstance(block.data, VideoAttachmentContent):
            raise ValueError("file/video: ожидается VideoAttachmentContent.")
        next_contents.append(
            MessageContentModel(
                type=block.type,
                data=VideoAttachmentContent(
                    file_id=block.data.file_id,
                    filename=block.data.filename,
                    mime_type=block.data.mime_type,
                    size=block.data.size,
                    duration_ms=block.data.duration_ms,
                    transcription_status=status,
                    transcription_text=transcription_text,
                    transcription_error=transcription_error,
                ),
                order=block.order,
            )
        )
        replaced = True
    if not replaced:
        raise ValueError("Сообщение не содержит file/video.")
    return next_contents


def _extract_video_info(contents: list[MessageContentModel]) -> VideoAttachmentContent:
    ordered = sorted(contents, key=lambda item: item.order)
    for block in ordered:
        if block.type != MessageContentType.FILE_VIDEO:
            continue
        if not isinstance(block.data, VideoAttachmentContent):
            raise ValueError("file/video: ожидается VideoAttachmentContent.")
        return block.data
    raise ValueError("Сообщение не содержит file/video.")


def _extract_audio_track_from_video_bytes(*, video_bytes: bytes, base_name: str) -> tuple[bytes, str]:
    if not video_bytes:
        raise ValueError("video_bytes не может быть пустым.")
    stem = Path(base_name).stem or "recording"
    with tempfile.TemporaryDirectory(prefix="sync-video-stt-") as work_dir:
        in_path = Path(work_dir) / "input.mp4"
        out_path = Path(work_dir) / "audio.mp3"
        in_path.write_bytes(video_bytes)
        ffmpeg_cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(in_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(out_path),
        ]
        ffmpeg_result = subprocess.run(
            ffmpeg_cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if ffmpeg_result.returncode != 0:
            stderr = ffmpeg_result.stderr.strip()
            raise RuntimeError(
                "Не удалось извлечь аудио из видео для STT. "
                f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
        audio_bytes = out_path.read_bytes()
        if len(audio_bytes) == 0:
            raise ValueError("Извлечённая аудиодорожка пуста.")
        return audio_bytes, f"{stem}-audio.mp3"


def _utc_iso_z(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _split_text_plain_chunks(full_text: str) -> list[str]:
    if full_text == "":
        return []
    lines = full_text.split("\n")
    chunks: list[str] = []
    buf = ""
    for line in lines:
        candidate = line if buf == "" else f"{buf}\n{line}"
        if len(candidate) > SYNC_MESSAGE_TEXT_MAX_CHARS:
            if buf != "":
                chunks.append(buf)
                buf = line
            while len(buf) > SYNC_MESSAGE_TEXT_MAX_CHARS:
                chunks.append(buf[:SYNC_MESSAGE_TEXT_MAX_CHARS])
                buf = buf[SYNC_MESSAGE_TEXT_MAX_CHARS:]
            continue
        buf = candidate
    if buf != "":
        chunks.append(buf)
    return chunks


@broker.task
async def handle_command(cmd: dict[str, Any]) -> dict[str, Any]:
    command = CommandEnvelope.model_validate(cmd)
    logger.info(
        "task handle_command started: id=%s type=%s actor=%s company=%s",
        command.id,
        command.type,
        command.actor_user_id,
        command.company_id,
    )
    return await dispatch_sync_command(command)


@broker.task
async def sync_finalize_recording_task(recording_id: str, company_id: str, actor_user_id: str) -> None:
    logger.info(
        "sync_finalize_recording_task start: recording_id=%s company_id=%s actor=%s",
        recording_id,
        company_id,
        actor_user_id,
    )
    container = get_sync_container()
    recording = await container.call_recording_repository.get(recording_id)
    if recording is None or recording.company_id != company_id:
        raise ValueError(f"Запись {recording_id} не найдена.")
    call = await container.call_repository.get_call(recording.call_id, company_id)
    if call.livekit_room_name is None:
        raise ValueError(f"У звонка {call.call_id} отсутствует livekit_room_name.")
    if recording.started_by_user_id is None or recording.started_by_user_id == "":
        raise ValueError("У записи не задан started_by_user_id.")

    async with traced_operation(
        "sync.calls.finalize_recording",
        event_type="sync.calls",
        operation_category="livekit_egress",
        billing_usage_type=UsageType.TOOL_CALL.value,
        billing_resource_name="tool:livekit_recording_finalize",
        billing_quantity=1,
        billing_pending_settlement=True,
        resource_type="sync_call_recording",
        resource_id=recording_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: recording.started_by_user_id,
            trace_attributes.ATTR_CALL_ID: recording.call_id,
            trace_attributes.ATTR_CHANNEL_ID: recording.channel_id,
            trace_attributes.ATTR_LIVEKIT_ROOM: call.livekit_room_name or "",
        },
    ) as finalize_span:
        try:
            settings = get_settings()
            raw_file_id = recording.raw_file_id or recording.recording_id
            egress_timeout_seconds = settings.calls.finalize_recording_egress_wait_timeout_seconds
            if recording.provider_job_id is None or recording.provider_job_id == "":
                raise ValueError(
                    f"У записи {recording.recording_id} отсутствует provider_job_id для поиска egress результата."
                )
            provider_job_id, raw_storage_url = await _resolve_livekit_egress_result(
                room_name=call.livekit_room_name,
                timeout_seconds=egress_timeout_seconds,
                expected_egress_id=recording.provider_job_id,
            )
            finalize_span.set_attribute(trace_attributes.ATTR_LIVEKIT_EGRESS_ID, provider_job_id)
            raw_storage_url = _normalize_storage_url_for_worker(
                storage_url=raw_storage_url,
                testing=bool(getattr(settings, "testing", False)),
            )
            logger.info(
                "sync_finalize_recording_task egress resolved: recording_id=%s egress_id=%s raw_storage_url=%s",
                recording.recording_id,
                provider_job_id,
                raw_storage_url,
            )
            parsed_storage_url = urlparse(raw_storage_url)
            raw_original_name = parsed_storage_url.path.rsplit("/", 1)[-1]
            if raw_original_name == "":
                raise ValueError(f"Не удалось определить имя файла egress из URL: {raw_storage_url}")
            raw_file = SyncFile(
                file_id=raw_file_id,
                company_id=company_id,
                original_name=raw_original_name,
                mime_type="video/mp4",
                size_bytes=0,
                storage_url=raw_storage_url,
                checksum=None,
            )
            existing_raw = await container.sync_file_repository.get(raw_file_id)
            if existing_raw is None:
                await container.sync_file_repository.create(raw_file)
            else:
                existing_raw.original_name = raw_original_name
                existing_raw.mime_type = "video/mp4"
                existing_raw.size_bytes = 0
                existing_raw.storage_url = raw_storage_url
                existing_raw.checksum = None
                await container.sync_file_repository.update(existing_raw)

            await container.call_recording_repository.mark_status(
                recording.recording_id,
                status="uploaded",
                provider_job_id=provider_job_id,
                raw_file_id=raw_file_id,
            )

            video_body = MessageCreate(
                thread_id=None,
                parent_message_id=None,
                contents=[
                    MessageContentModel(
                        type=MessageContentType.FILE_VIDEO,
                        data=VideoAttachmentContent(
                            file_id=raw_file_id,
                            filename=raw_original_name,
                            mime_type="video/mp4",
                            size=0,
                            duration_ms=None,
                            transcription_status=AudioTranscriptionStatus.IDLE,
                            transcription_text=None,
                            transcription_error=None,
                        ),
                        order=0,
                    )
                ],
                mentioned_user_ids=None,
                call_id=recording.call_id,
            )
            send_payload = MessagesSendPayload(channel_id=recording.channel_id, body=video_body)
            cmd = CommandEnvelope(
                id=uuid4().hex,
                type="messages.send",
                actor_user_id=recording.started_by_user_id,
                company_id=company_id,
                payload=send_payload.model_dump(mode="json"),
            )
            await dispatch_sync_command(cmd)
            logger.info(
                "sync_finalize_recording_task posted video message: recording_id=%s channel_id=%s",
                recording.recording_id,
                recording.channel_id,
            )
        except Exception as exc:
            logger.error(
                "sync_finalize_recording_task failed: recording_id=%s error=%s",
                recording_id,
                str(exc),
                exc_info=True,
            )
            await container.call_recording_repository.mark_status(
                recording.recording_id,
                status="failed",
                error=str(exc),
            )
            failed_row = await container.call_recording_repository.get(recording_id)
            if failed_row is not None:
                await publish_realtime_events([event_call_recording_failed(_recording_read_from_entity(failed_row))])
            raise


async def transcribe_audio_message_core(
    *,
    channel_id: str,
    message_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    if channel_id == "":
        raise ValueError("channel_id обязателен.")
    if message_id == "":
        raise ValueError("message_id обязателен.")
    if company_id == "":
        raise ValueError("company_id обязателен.")
    if actor_user_id == "":
        raise ValueError("actor_user_id обязателен.")

    container = get_sync_container()
    source_message = await container.message_repository.get_by_id_for_company(message_id, company_id)
    if source_message is None:
        raise ValueError(f"Сообщение {message_id} не найдено.")
    if source_message.channel_id != channel_id:
        raise ValueError("Сообщение не принадлежит указанному каналу.")
    if source_message.deleted_at is not None:
        raise ValueError("Нельзя расшифровать удалённое сообщение.")

    rows = await container.message_repository.list_contents(message_id)
    source_contents = [
        MessageContentModel.model_validate({"type": row.type, "data": row.data, "order": row.order})
        for row in rows
    ]
    audio_info = _extract_audio_info(source_contents)
    if audio_info.file_id == "":
        raise ValueError("file/audio.file_id обязателен.")
    if audio_info.filename == "":
        raise ValueError("file/audio.filename обязателен.")
    if audio_info.mime_type == "":
        raise ValueError("file/audio.mime_type обязателен.")

    settings = get_settings()
    redis_url = settings.database.redis_url
    if redis_url is None or redis_url.strip() == "":
        raise ValueError("database.redis_url обязателен для sync_transcribe_audio_message_task.")

    timeout_seconds = settings.stt.cloud_ru.timeout
    if timeout_seconds <= 0:
        raise ValueError("stt.cloud_ru.timeout должен быть больше 0.")

    sync_base_url = settings.server.get_service_url("sync")
    if not isinstance(sync_base_url, str) or sync_base_url == "":
        raise ValueError("URL sync сервиса не задан.")
    file_download_url = f"{sync_base_url.rstrip('/')}/sync/api/v1/files/download/{audio_info.file_id}"
    auth_headers = _build_interservice_auth_headers(
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    r = redis_async.from_url(redis_url)
    lock_key = f"sync:transcribe_audio:{company_id}:{message_id}"
    token = uuid4().hex
    lock_ttl = settings.transcribe_audio_redis_lock_ttl_seconds
    acquired = await r.set(lock_key, token, nx=True, ex=lock_ttl)
    if not acquired:
        await r.aclose()
        logger.info(
            "transcribe_audio: пропуск, сообщение уже обрабатывается другим воркером message_id=%s",
            message_id,
        )
        return
    try:
        try:
            async with traced_operation(
                "sync.stt.transcribe_audio_message",
                event_type="sync.stt",
                operation_category="stt",
                billing_usage_type=UsageType.TOOL_CALL.value,
                billing_resource_name="tool:stt_sync_message",
                billing_quantity=1,
                billing_pending_settlement=True,
                resource_type="sync_message",
                resource_id=message_id,
                extra_attributes={
                    trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                    trace_attributes.ATTR_USER_ID: actor_user_id,
                    trace_attributes.ATTR_CHANNEL_ID: channel_id,
                },
            ) as stt_span:
                stt_span.set_attribute(trace_attributes.ATTR_STT_PROVIDER, settings.stt.provider)
                async with get_httpx_client(timeout=timeout_seconds) as client:
                    response = await client.get(file_download_url, headers=auth_headers)
                response.raise_for_status()
                if not response.content:
                    raise ValueError("Файл аудиосообщения пустой.")
                audio_len = len(response.content)
                stt_span.set_attribute(trace_attributes.ATTR_STT_AUDIO_BYTES, audio_len)

                transcript_text = await _transcribe_audio_with_chunking(
                    job_id=message_id,
                    audio_bytes=response.content,
                    file_name=audio_info.filename,
                    mime_type=audio_info.mime_type,
                    language=settings.stt.cloud_ru.language,
                )
                if transcript_text.strip() == "":
                    raise ValueError("STT вернул пустую транскрипцию аудиосообщения.")

                done_contents = _replace_audio_transcription(
                    contents=source_contents,
                    status=AudioTranscriptionStatus.DONE,
                    transcription_text=transcript_text,
                    transcription_error=None,
                )
                await container.message_repository.replace_message_contents(
                    message_id=message_id,
                    contents=done_contents,
                    edited_at=datetime.now(tz=UTC),
                )
                done_message = await _load_message_read(
                    container,
                    message_id=message_id,
                    company_id=company_id,
                )
                await publish_realtime_events([event_message_updated(done_message)])
        except Exception as exc:
            failed_contents = _replace_audio_transcription(
                contents=source_contents,
                status=AudioTranscriptionStatus.FAILED,
                transcription_text=None,
                transcription_error=str(exc),
            )
            await container.message_repository.replace_message_contents(
                message_id=message_id,
                contents=failed_contents,
                edited_at=datetime.now(tz=UTC),
            )
            failed_message = await _load_message_read(
                container,
                message_id=message_id,
                company_id=company_id,
            )
            await publish_realtime_events([event_message_updated(failed_message)])
            logger.warning(
                "Расшифровка аудиосообщения завершилась ошибкой: channel_id=%s message_id=%s error=%s",
                channel_id,
                message_id,
                str(exc),
            )
    finally:
        await r.eval(_TRANSCRIBE_AUDIO_LOCK_RELEASE_LUA, 1, lock_key, token)
        await r.aclose()


@broker.task
async def sync_transcribe_audio_message_task(
    *,
    channel_id: str,
    message_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    await transcribe_audio_message_core(
        channel_id=channel_id,
        message_id=message_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
    )


async def transcribe_video_message_core(
    *,
    channel_id: str,
    message_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    container = get_sync_container()
    source_message = await container.message_repository.get_by_id_for_company(message_id, company_id)
    if source_message is None:
        raise ValueError(f"Сообщение {message_id} не найдено.")
    if source_message.channel_id != channel_id:
        raise ValueError("Сообщение не принадлежит указанному каналу.")
    if source_message.deleted_at is not None:
        raise ValueError("Нельзя расшифровать удалённое сообщение.")

    rows = await container.message_repository.list_contents(message_id)
    source_contents = [
        MessageContentModel.model_validate({"type": row.type, "data": row.data, "order": row.order})
        for row in rows
    ]
    video_info = _extract_video_info(source_contents)
    if video_info.file_id == "":
        raise ValueError("file/video.file_id обязателен.")
    if video_info.filename == "":
        raise ValueError("file/video.filename обязателен.")

    settings = get_settings()
    timeout_seconds = settings.stt.cloud_ru.timeout
    if timeout_seconds <= 0:
        raise ValueError("stt.cloud_ru.timeout должен быть больше 0.")

    sync_base_url = settings.server.get_service_url("sync")
    if not isinstance(sync_base_url, str) or sync_base_url == "":
        raise ValueError("URL sync сервиса не задан.")
    file_download_url = f"{sync_base_url.rstrip('/')}/sync/api/v1/files/download/{video_info.file_id}"
    auth_headers = _build_interservice_auth_headers(
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    try:
        async with traced_operation(
            "sync.stt.transcribe_video_message",
            event_type="sync.stt",
            operation_category="stt",
            billing_usage_type=UsageType.TOOL_CALL.value,
            billing_resource_name="tool:stt_sync_message",
            billing_quantity=1,
            billing_pending_settlement=True,
            resource_type="sync_message",
            resource_id=message_id,
            extra_attributes={
                trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
                trace_attributes.ATTR_USER_ID: actor_user_id,
                trace_attributes.ATTR_CHANNEL_ID: channel_id,
            },
        ) as video_stt_span:
            video_stt_span.set_attribute(trace_attributes.ATTR_STT_PROVIDER, settings.stt.provider)
            async with get_httpx_client(timeout=timeout_seconds) as client:
                response = await client.get(file_download_url, headers=auth_headers)
            response.raise_for_status()
            if not response.content:
                raise ValueError("Файл видеосообщения пустой.")
            video_stt_span.set_attribute(trace_attributes.ATTR_STT_AUDIO_BYTES, len(response.content))

            audio_bytes, audio_name = _extract_audio_track_from_video_bytes(
                video_bytes=response.content,
                base_name=video_info.filename,
            )
            transcript_text = await _transcribe_audio_with_chunking(
                job_id=message_id,
                audio_bytes=audio_bytes,
                file_name=audio_name,
                mime_type="audio/mpeg",
                language=settings.stt.cloud_ru.language,
            )
            if transcript_text.strip() == "":
                raise ValueError("STT вернул пустую транскрипцию видеосообщения.")

            done_contents = _replace_video_transcription(
                contents=source_contents,
                status=AudioTranscriptionStatus.DONE,
                transcription_text=transcript_text,
                transcription_error=None,
            )
            await container.message_repository.replace_message_contents(
                message_id=message_id,
                contents=done_contents,
                edited_at=datetime.now(tz=UTC),
            )
            done_message = await _load_message_read(
                container,
                message_id=message_id,
                company_id=company_id,
            )
            await publish_realtime_events([event_message_updated(done_message)])
    except Exception as exc:
        failed_contents = _replace_video_transcription(
            contents=source_contents,
            status=AudioTranscriptionStatus.FAILED,
            transcription_text=None,
            transcription_error=str(exc),
        )
        await container.message_repository.replace_message_contents(
            message_id=message_id,
            contents=failed_contents,
            edited_at=datetime.now(tz=UTC),
        )
        failed_message = await _load_message_read(
            container,
            message_id=message_id,
            company_id=company_id,
        )
        await publish_realtime_events([event_message_updated(failed_message)])
        logger.warning(
            "Расшифровка видеосообщения завершилась ошибкой: channel_id=%s message_id=%s error=%s",
            channel_id,
            message_id,
            str(exc),
        )


@broker.task
async def sync_transcribe_video_message_task(
    *,
    channel_id: str,
    message_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    await transcribe_video_message_core(
        channel_id=channel_id,
        message_id=message_id,
        company_id=company_id,
        actor_user_id=actor_user_id,
    )


@broker.task
async def sync_aggregate_call_transcript_task(
    *,
    channel_id: str,
    call_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    if channel_id == "" or call_id == "" or company_id == "" or actor_user_id == "":
        raise ValueError("channel_id, call_id, company_id и actor_user_id обязательны.")

    async with traced_operation(
        "sync.calls.aggregate_transcript",
        event_type="sync.calls",
        operation_category="sync_command",
        resource_type="sync_call",
        resource_id=call_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_USER_ID: actor_user_id,
            trace_attributes.ATTR_CHANNEL_ID: channel_id,
            trace_attributes.ATTR_CALL_ID: call_id,
        },
    ) as aggregate_span:
        container = get_sync_container()
        rows = await container.message_repository.list_root_lane_by_call(
            channel_id=channel_id,
            call_id=call_id,
            company_id=company_id,
        )
        aggregate_span.set_attribute("platform.sync.call_aggregate_lane_count", len(rows))
        for m in rows:
            content_rows = await container.message_repository.list_contents(m.message_id)
            contents = [
                MessageContentModel.model_validate({"type": r.type, "data": r.data, "order": r.order})
                for r in content_rows
            ]
            has_audio = any(c.type == MessageContentType.FILE_AUDIO for c in contents)
            has_video = any(c.type == MessageContentType.FILE_VIDEO for c in contents)
            if has_audio:
                audio = _extract_audio_info(contents)
                if audio.transcription_status != AudioTranscriptionStatus.DONE:
                    await transcribe_audio_message_core(
                        channel_id=channel_id,
                        message_id=m.message_id,
                        company_id=company_id,
                        actor_user_id=actor_user_id,
                    )
            if has_video:
                video = _extract_video_info(
                    [
                        MessageContentModel.model_validate({"type": r.type, "data": r.data, "order": r.order})
                        for r in await container.message_repository.list_contents(m.message_id)
                    ]
                )
                if video.transcription_status != AudioTranscriptionStatus.DONE:
                    await transcribe_video_message_core(
                        channel_id=channel_id,
                        message_id=m.message_id,
                        company_id=company_id,
                        actor_user_id=actor_user_id,
                    )

        out_lines: list[str] = []
        fresh_rows = await container.message_repository.list_root_lane_by_call(
            channel_id=channel_id,
            call_id=call_id,
            company_id=company_id,
        )
        for m in fresh_rows:
            content_rows = await container.message_repository.list_contents(m.message_id)
            contents = [
                MessageContentModel.model_validate({"type": r.type, "data": r.data, "order": r.order})
                for r in content_rows
            ]
            only_boundary = (
                len(contents) == 1
                and contents[0].type == MessageContentType.CALL_BOUNDARY
            )
            if only_boundary:
                continue

            sender = await sender_brief_for_message(container.user_repository, m.sender_user_id)
            label = sender.display_name
            ts = _utc_iso_z(m.sent_at)
            parts: list[str] = []
            for c in sorted(contents, key=lambda x: x.order):
                if c.type == MessageContentType.TEXT_PLAIN:
                    if isinstance(c.data, TextPlainContent) and c.data.body.strip() != "":
                        parts.append(c.data.body.strip())
                elif c.type == MessageContentType.FILE_AUDIO:
                    if isinstance(c.data, AudioAttachmentContent):
                        if c.data.transcription_text and c.data.transcription_text.strip() != "":
                            parts.append(c.data.transcription_text.strip())
                elif c.type == MessageContentType.FILE_VIDEO:
                    if isinstance(c.data, VideoAttachmentContent):
                        if c.data.transcription_text and c.data.transcription_text.strip() != "":
                            parts.append(c.data.transcription_text.strip())
            if len(parts) == 0:
                continue
            body = " ".join(parts)
            out_lines.append(f"[{label}][{ts}] — {body}")

        full_text = "\n".join(out_lines)
        if full_text.strip() == "":
            full_text = _sync_call_aggregate_empty_body()

        chunks = _split_text_plain_chunks(full_text)
        content_blocks = [
            MessageContentModel(
                type=MessageContentType.TEXT_PLAIN,
                data=TextPlainContent(body=chunk, mentions=None),
                order=idx,
            )
            for idx, chunk in enumerate(chunks)
        ]
        agg_body = MessageCreate(
            thread_id=None,
            parent_message_id=None,
            contents=content_blocks,
            mentioned_user_ids=None,
            call_id=call_id,
        )
        send_payload = MessagesSendPayload(channel_id=channel_id, body=agg_body)
        cmd = CommandEnvelope(
            id=uuid4().hex,
            type="messages.send",
            actor_user_id=actor_user_id,
            company_id=company_id,
            payload=send_payload.model_dump(mode="json"),
        )
        await dispatch_sync_command(cmd)


def _speech_to_chat_poll_sleep_seconds(*, is_continuation: bool) -> float:
    stc = get_settings().calls.speech_to_chat
    return float(stc.poll_interval_seconds if is_continuation else stc.poll_initial_delay_seconds)


@broker.task
async def sync_speech_to_chat_poll_task(
    *,
    call_id: str,
    company_id: str,
    is_continuation: bool = False,
    delay_override_seconds: float | None = None,
) -> None:
    """Keyword-only args: иначе SessionLockMiddleware принимает company_id за session_id.

    Первый kiq (после invite) ждёт POLL_INITIAL; следующие тики — POLL_INTERVAL.
    delay_override_seconds — если lock poll занят, следующий тик с backoff из конфига.
    """
    if delay_override_seconds is not None:
        await asyncio.sleep(delay_override_seconds)
    else:
        await asyncio.sleep(_speech_to_chat_poll_sleep_seconds(is_continuation=is_continuation))
    from apps.sync.realtime.speech_to_chat_workflow import run_speech_to_chat_poll_cycle

    async with traced_operation(
        "sync.speech_to_chat.poll_cycle",
        event_type="sync.speech_to_chat",
        operation_category="sync_command",
        resource_type="sync_call",
        resource_id=call_id,
        extra_attributes={
            trace_attributes.ATTR_TENANT_COMPANY_ID: company_id,
            trace_attributes.ATTR_CALL_ID: call_id,
        },
    ):
        outcome = await run_speech_to_chat_poll_cycle(call_id=call_id, company_id=company_id)
    if outcome.schedule_next:
        stc = get_settings().calls.speech_to_chat
        next_delay = (
            stc.poll_lock_busy_retry_seconds
            if outcome.next_delay == "lock_busy"
            else None
        )
        await sync_speech_to_chat_poll_task.kiq(
            call_id=call_id,
            company_id=company_id,
            is_continuation=True,
            delay_override_seconds=next_delay,
        )
