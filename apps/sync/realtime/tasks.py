"""TaskIQ задачи realtime слоя Sync."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import mimetypes
from typing import Any
from urllib.parse import urlparse

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncCallSpeakerSegment, SyncFile
from apps.sync.models.meetings import CallMeetingRead
from apps.sync.models.messages import (
    AudioAttachmentContent,
    AudioTranscriptionStatus,
    MessageContentModel,
    MessageContentType,
)
from apps.sync.models.common import UserBrief
from apps.sync.realtime.broker import broker
from apps.sync.realtime.command_dispatch import dispatch_sync_command
from apps.sync.realtime.commands import CommandEnvelope
from apps.sync.realtime.events import (
    event_call_export_crm_done,
    event_call_export_crm_failed,
    event_call_summary_ready,
    event_call_summary_failed,
    event_call_transcript_failed,
    event_call_transcript_ready,
    event_message_updated,
)
from apps.sync.message_read_helpers import message_read_from_entity
from apps.sync.realtime.publish_events import publish_realtime_events
from core.calls.livekit_client import LiveKitClient
from core.clients.a2a_client import A2AClient
from core.clients.stt_client import STTClientFactory
from core.config import get_settings
from core.files.s3_client import S3ClientFactory
from core.http import get_httpx_client
from core.logging import get_logger
from core.utils.tokens import get_token_service

logger = get_logger(__name__)


def _normalize_mime_type(raw_mime_type: str | None) -> str | None:
    if raw_mime_type is None:
        return None
    if raw_mime_type == "":
        return None
    return raw_mime_type.split(";", 1)[0].strip().lower()


def _looks_like_text_error_payload(payload: bytes) -> str | None:
    if len(payload) == 0:
        return "пустое тело ответа"
    probe = payload[:4096]
    try:
        text = probe.decode("utf-8", errors="ignore").strip()
    except UnicodeDecodeError:
        return None
    if text == "":
        return None
    normalized = text.lower()
    error_markers = (
        "error opening <_io.bytesio object>",
        "format not recognised",
        "<html",
        "<!doctype html",
        "<?xml",
        "<error>",
        "<code>nosuchkey</code>",
        "accessdenied",
        "\"error\"",
        "\"errors\"",
    )
    for marker in error_markers:
        if marker in normalized:
            compact = " ".join(text.split())
            snippet = compact[:200]
            return f"вместо медиаданных получен текст ошибки: {snippet}"
    return None


def _validate_recording_media_payload(
    *,
    payload: bytes,
    response_content_type: str | None,
    source_url: str,
) -> None:
    normalized_mime_type = _normalize_mime_type(response_content_type)
    if normalized_mime_type is not None:
        if (
            not normalized_mime_type.startswith("audio/")
            and not normalized_mime_type.startswith("video/")
            and normalized_mime_type != "application/octet-stream"
        ):
            raise ValueError(
                "Источник записи вернул неподдерживаемый content-type: "
                f"{normalized_mime_type}. source_url={source_url}"
            )
    error_description = _looks_like_text_error_payload(payload)
    if error_description is not None:
        raise ValueError(
            f"Источник записи вернул невалидный файл ({error_description}). source_url={source_url}"
        )


async def _download_recording_bytes(*, source_url: str, timeout_seconds: float) -> tuple[bytes, str | None]:
    """Скачивает запись с коротким ожиданием появления файла после stop recording."""
    wait_timeout_seconds = 90.0
    poll_interval_seconds = 3.0
    elapsed_seconds = 0.0
    last_status_code: int | None = None

    while True:
        logger.info(
            "download_recording_bytes poll: source_url=%s elapsed=%.1fs timeout=%.1fs",
            source_url,
            elapsed_seconds,
            wait_timeout_seconds,
        )
        async with get_httpx_client(timeout=timeout_seconds) as client:
            response = await client.get(source_url)
        last_status_code = response.status_code
        logger.info(
            "download_recording_bytes response: source_url=%s status=%s bytes=%s",
            source_url,
            response.status_code,
            len(response.content),
        )
        if response.status_code == 200:
            if not response.content:
                raise ValueError("Источник записи вернул пустое тело.")
            _validate_recording_media_payload(
                payload=response.content,
                response_content_type=response.headers.get("content-type"),
                source_url=source_url,
            )
            return response.content, response.headers.get("content-type")
        if response.status_code != 404:
            response.raise_for_status()
        if elapsed_seconds >= wait_timeout_seconds:
            break
        await asyncio.sleep(poll_interval_seconds)
        elapsed_seconds += poll_interval_seconds

    raise RuntimeError(
        "Файл записи не появился после остановки звонка. "
        f"source_url={source_url}, last_status={last_status_code}. "
        "Проверьте egress-пайплайн LiveKit и путь выгрузки записи."
    )


def _host_aliases(hostname: str) -> set[str]:
    aliases = {hostname}
    if hostname == "localhost" or hostname == "127.0.0.1":
        aliases.add("host.docker.internal")
    if hostname == "host.docker.internal":
        aliases.update({"localhost", "127.0.0.1"})
    return aliases


async def _try_download_recording_bytes_from_s3(source_url: str) -> tuple[bytes, str | None] | None:
    parsed = urlparse(source_url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.hostname is None:
        return None
    if parsed.path == "" or parsed.path == "/":
        return None
    path_without_slash = parsed.path.lstrip("/")
    if "/" not in path_without_slash:
        return None
    bucket_from_url, object_key = path_without_slash.split("/", 1)
    if bucket_from_url == "" or object_key == "":
        return None

    settings = get_settings()
    source_hosts = _host_aliases(parsed.hostname)
    source_port = parsed.port

    for bucket_alias, bucket_config in settings.s3.buckets.items():
        real_bucket_name = bucket_config.bucket_name or bucket_alias
        if real_bucket_name != bucket_from_url:
            continue
        endpoint_url = bucket_config.endpoint_url
        if endpoint_url is None or endpoint_url == "":
            continue
        endpoint_parsed = urlparse(endpoint_url)
        if endpoint_parsed.scheme == "":
            continue
        if endpoint_parsed.hostname is None:
            continue
        endpoint_hosts = _host_aliases(endpoint_parsed.hostname)
        endpoint_port = endpoint_parsed.port
        if source_hosts.isdisjoint(endpoint_hosts):
            continue
        if source_port != endpoint_port:
            continue

        s3_client = S3ClientFactory.create_client_for_bucket(bucket_alias)
        try:
            payload = await s3_client.download_bytes(key=object_key, bucket=real_bucket_name)
        finally:
            await s3_client.close()
        content_type, _ = mimetypes.guess_type(object_key)
        _validate_recording_media_payload(
            payload=payload,
            response_content_type=content_type,
            source_url=source_url,
        )
        return payload, content_type

    return None


async def build_call_transcript_text(meeting_id: str, source_url: str) -> str:
    """Строит текст транскрипта из источника записи."""
    if not isinstance(source_url, str) or source_url == "":
        raise ValueError("source_url обязателен для транскрипции.")
    if not source_url.startswith("http://") and not source_url.startswith("https://"):
        raise ValueError(f"Неподдерживаемый source_url для STT: {source_url}")

    parsed = urlparse(source_url)
    file_name = parsed.path.rsplit("/", 1)[-1]
    if file_name == "":
        raise ValueError(f"Не удалось определить имя файла из source_url: {source_url}")

    settings = get_settings()
    timeout_seconds = settings.stt.cloud_ru.timeout
    if timeout_seconds <= 0:
        raise ValueError("stt.cloud_ru.timeout должен быть больше 0.")

    downloaded_from_s3 = await _try_download_recording_bytes_from_s3(source_url)
    if downloaded_from_s3 is None:
        audio_bytes, response_content_type = await _download_recording_bytes(
            source_url=source_url,
            timeout_seconds=timeout_seconds,
        )
    else:
        audio_bytes, response_content_type = downloaded_from_s3

    guessed_mime_type, _ = mimetypes.guess_type(file_name)
    mime_type = response_content_type or guessed_mime_type
    if not isinstance(mime_type, str) or mime_type == "":
        raise ValueError(f"Не удалось определить mime type записи: {file_name}")

    stt_client = STTClientFactory.create_client()
    transcript_result = await stt_client.transcribe_audio(
        audio_bytes=audio_bytes,
        file_name=file_name,
        mime_type=mime_type,
        language=settings.stt.cloud_ru.language,
    )
    if transcript_result.status != AudioTranscriptionStatus.DONE:
        raise ValueError(
            "STT вернул неуспешный статус транскрипции "
            f"для встречи {meeting_id}: {transcript_result.status.value}."
        )
    transcript_text = transcript_result.text
    if transcript_text.strip() == "":
        raise ValueError(f"STT вернул пустую транскрипцию для встречи {meeting_id}.")
    return transcript_text


def _build_interservice_auth_headers(actor_user_id: str, company_id: str) -> dict[str, str]:
    """Строит auth заголовки для межсервисных вызовов из worker-задач."""
    token = get_token_service().create_token(actor_user_id, company_id=company_id)
    return {
        "Authorization": f"Bearer {token}",
        "X-Company-Id": company_id,
        "X-User-Id": actor_user_id,
    }


def _normalize_http_base_url(url: str) -> str:
    """Нормализует URL источника записи к HTTP(S)."""
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

    wait_timeout_seconds = 90.0
    poll_interval_seconds = 3.0
    elapsed_seconds = 0.0
    last_observed = "none"
    settings = get_settings()
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


async def _load_message_read(container, *, message_id: str, company_id: str):
    message_entity = await container.message_repository.get_by_id_for_company(message_id, company_id)
    if message_entity is None:
        raise ValueError(f"Сообщение {message_id} не найдено.")
    rows = await container.message_repository.list_contents(message_id)
    contents = [
        MessageContentModel.model_validate({"type": row.type, "data": row.data, "order": row.order})
        for row in rows
    ]
    users_by_id = await container.user_repository.get_many([message_entity.sender_user_id])
    sender_user = users_by_id.get(message_entity.sender_user_id)
    if sender_user is None:
        sender = UserBrief(
            user_id=message_entity.sender_user_id,
            display_name=message_entity.sender_user_id,
            avatar_url=None,
        )
    else:
        sender = UserBrief(
            user_id=sender_user.user_id,
            display_name=sender_user.name,
            avatar_url=sender_user.avatar_url,
        )
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


@broker.task
async def handle_command(cmd: dict[str, Any]) -> dict[str, Any]:
    """Обработка realtime команды в sync-worker."""
    command = CommandEnvelope.model_validate(cmd)
    logger.info(
        "task handle_command started: id=%s type=%s actor=%s company=%s",
        command.id, command.type, command.actor_user_id, command.company_id,
    )
    return await dispatch_sync_command(command)


@broker.task
async def sync_finalize_recording_task(recording_id: str, company_id: str, actor_user_id: str) -> None:
    """Финализирует запись: создает raw файл, встречу и запускает транскрипцию."""
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

    try:
        settings = get_settings()
        raw_file_id = recording.raw_file_id or recording.recording_id
        egress_timeout_seconds = settings.stt.cloud_ru.timeout
        if recording.provider_job_id is None or recording.provider_job_id == "":
            raise ValueError(
                f"У записи {recording.recording_id} отсутствует provider_job_id для поиска egress результата."
            )
        provider_job_id, raw_storage_url = await _resolve_livekit_egress_result(
            room_name=call.livekit_room_name,
            timeout_seconds=egress_timeout_seconds,
            expected_egress_id=recording.provider_job_id,
        )
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

        meeting = await container.call_meeting_repository.get_by_recording(recording.recording_id, company_id)
        if meeting is None:
            from uuid import uuid4
            from datetime import UTC, datetime
            meeting = await container.call_meeting_repository.create(
                container.call_meeting_repository.model_class(
                    meeting_id=uuid4().hex,
                    call_id=recording.call_id,
                    recording_id=recording.recording_id,
                    company_id=company_id,
                    channel_id=recording.channel_id,
                    space_id=recording.space_id,
                    summary_json={},
                    export_status="pending",
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                )
            )

        await sync_transcribe_recording_task.kiq(
            meeting_id=meeting.meeting_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )
        logger.info(
            "sync_finalize_recording_task queued transcribe: meeting_id=%s recording_id=%s",
            meeting.meeting_id,
            recording.recording_id,
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
        failed_meeting = await container.call_meeting_repository.get_by_recording(recording.recording_id, company_id)
        if failed_meeting is not None:
            await container.call_meeting_repository.set_export_status(
                failed_meeting.meeting_id,
                status="failed",
                target_namespace=failed_meeting.export_target_namespace,
            )
            failed_meeting = await container.call_meeting_repository.get(failed_meeting.meeting_id)
            if failed_meeting is not None:
                failed_payload = CallMeetingRead(
                    meeting_id=failed_meeting.meeting_id,
                    call_id=failed_meeting.call_id,
                    recording_id=failed_meeting.recording_id,
                    channel_id=failed_meeting.channel_id,
                    space_id=failed_meeting.space_id,
                    transcript_file_id=failed_meeting.transcript_file_id,
                    transcript_text_file_id=failed_meeting.transcript_text_file_id,
                    summary_json=failed_meeting.summary_json or {},
                    export_status=failed_meeting.export_status,
                    export_target_namespace=failed_meeting.export_target_namespace,
                    created_at=failed_meeting.created_at,
                    updated_at=failed_meeting.updated_at,
                )
                await publish_realtime_events(
                    [event_call_transcript_failed(failed_payload, str(exc))]
                )
        raise


@broker.task
async def sync_transcribe_recording_task(meeting_id: str, company_id: str, actor_user_id: str) -> None:
    """Создает текст транскрипта и сегменты речи, затем запускает summary."""
    logger.info(
        "sync_transcribe_recording_task start: meeting_id=%s company_id=%s actor=%s",
        meeting_id,
        company_id,
        actor_user_id,
    )
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    try:
        if meeting.recording_id is None:
            raise ValueError(f"У встречи {meeting_id} отсутствует recording_id.")
        recording = await container.call_recording_repository.get(meeting.recording_id)
        if recording is None or recording.company_id != company_id:
            raise ValueError(f"Запись {meeting.recording_id} не найдена.")
        if recording.raw_file_id is None:
            raise ValueError(f"У записи {recording.recording_id} отсутствует raw_file_id.")
        raw_file = await container.sync_file_repository.get(recording.raw_file_id)
        if raw_file is None:
            raise ValueError(f"Файл {recording.raw_file_id} не найден.")

        transcript_text = await build_call_transcript_text(
            meeting_id=meeting.meeting_id,
            source_url=raw_file.storage_url,
        )
        logger.info(
            "sync_transcribe_recording_task transcript ready: meeting_id=%s chars=%s source_url=%s",
            meeting.meeting_id,
            len(transcript_text),
            raw_file.storage_url,
        )
        if transcript_text.strip() == "":
            raise ValueError(f"Пустой транскрипт для встречи {meeting.meeting_id}.")
        settings = get_settings()
        if not settings.s3.enabled:
            raise ValueError("S3 отключен: сохранение транскрипта недоступно.")
        default_bucket_key = settings.s3.default_bucket
        if default_bucket_key == "":
            raise ValueError("s3.default_bucket не настроен.")
        if default_bucket_key not in settings.s3.buckets:
            raise ValueError(f"Конфиг S3 bucket '{default_bucket_key}' не найден.")
        bucket_config = settings.s3.buckets[default_bucket_key]
        if not bucket_config.enabled:
            raise ValueError(f"S3 bucket '{default_bucket_key}' выключен.")
        real_bucket_name = bucket_config.bucket_name or default_bucket_key
        if real_bucket_name == "":
            raise ValueError("Имя S3 bucket для транскрипта не может быть пустым.")
        transcript_s3_key = f"sync-meetings/{company_id}/{meeting.meeting_id}/transcript.txt"
        transcript_bytes = transcript_text.encode("utf-8")
        s3_client = S3ClientFactory.create_client_for_bucket(default_bucket_key)
        await s3_client.upload_bytes(
            data=transcript_bytes,
            key=transcript_s3_key,
            bucket=real_bucket_name,
            content_type="text/plain; charset=utf-8",
        )
        transcript_storage_url = s3_client.get_public_url(transcript_s3_key, bucket=real_bucket_name)
        transcript_file_id = f"{meeting.meeting_id}-transcript-txt"
        transcript_file = SyncFile(
            file_id=transcript_file_id,
            company_id=company_id,
            original_name=f"{meeting.meeting_id}.txt",
            mime_type="text/plain",
            size_bytes=len(transcript_bytes),
            storage_url=transcript_storage_url,
            checksum=None,
        )
        existing_transcript_file = await container.sync_file_repository.get(transcript_file_id)
        if existing_transcript_file is None:
            await container.sync_file_repository.create(transcript_file)
        else:
            existing_transcript_file.original_name = transcript_file.original_name
            existing_transcript_file.mime_type = transcript_file.mime_type
            existing_transcript_file.size_bytes = transcript_file.size_bytes
            existing_transcript_file.storage_url = transcript_file.storage_url
            existing_transcript_file.checksum = transcript_file.checksum
            await container.sync_file_repository.update(existing_transcript_file)

        from datetime import UTC, datetime
        from sqlalchemy import update
        async with container.sync_db.session() as session:
            await session.execute(
                update(container.call_meeting_repository.model_class)
                .where(container.call_meeting_repository.model_class.meeting_id == meeting.meeting_id)
                .values(
                    transcript_file_id=transcript_file_id,
                    transcript_text_file_id=transcript_file_id,
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
        updated_meeting = await container.call_meeting_repository.get(meeting.meeting_id)
        if updated_meeting is None:
            raise RuntimeError(f"Встреча {meeting.meeting_id} не найдена после записи транскрипта.")
        meeting_payload = CallMeetingRead(
            meeting_id=updated_meeting.meeting_id,
            call_id=updated_meeting.call_id,
            recording_id=updated_meeting.recording_id,
            channel_id=updated_meeting.channel_id,
            space_id=updated_meeting.space_id,
            transcript_file_id=updated_meeting.transcript_file_id,
            transcript_text_file_id=updated_meeting.transcript_text_file_id,
            summary_json=updated_meeting.summary_json or {},
            export_status=updated_meeting.export_status,
            export_target_namespace=updated_meeting.export_target_namespace,
            created_at=updated_meeting.created_at,
            updated_at=updated_meeting.updated_at,
        )
        await publish_realtime_events([event_call_transcript_ready(meeting_payload)])

        segments = [
            SyncCallSpeakerSegment(
                segment_id=f"{meeting.meeting_id}-seg-1",
                meeting_id=meeting.meeting_id,
                company_id=company_id,
                speaker_identity="system",
                speaker_type="user",
                speaker_user_id="system",
                speaker_guest_name=None,
                started_ms=0,
                ended_ms=1500,
                text="Начат автоматический pipeline транскрипции.",
            )
        ]
        await container.call_speaker_segment_repository.replace_for_meeting(
            meeting_id=meeting.meeting_id,
            company_id=company_id,
            segments=segments,
        )
        await sync_summarize_transcript_task.kiq(
            meeting_id=meeting.meeting_id,
            company_id=company_id,
            actor_user_id=actor_user_id,
        )
        logger.info(
            "sync_transcribe_recording_task queued summary: meeting_id=%s",
            meeting.meeting_id,
        )
    except Exception as exc:
        logger.error(
            "sync_transcribe_recording_task failed: meeting_id=%s error=%s",
            meeting_id,
            str(exc),
            exc_info=True,
        )
        if meeting.recording_id is not None:
            await container.call_recording_repository.mark_status(
                meeting.recording_id,
                status="failed",
                error=str(exc),
            )
        failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            await container.call_meeting_repository.set_export_status(
                failed_meeting.meeting_id,
                status="failed",
                target_namespace=failed_meeting.export_target_namespace,
            )
            failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            failed_payload = CallMeetingRead(
                meeting_id=failed_meeting.meeting_id,
                call_id=failed_meeting.call_id,
                recording_id=failed_meeting.recording_id,
                channel_id=failed_meeting.channel_id,
                space_id=failed_meeting.space_id,
                transcript_file_id=failed_meeting.transcript_file_id,
                transcript_text_file_id=failed_meeting.transcript_text_file_id,
                summary_json=failed_meeting.summary_json or {},
                export_status=failed_meeting.export_status,
                export_target_namespace=failed_meeting.export_target_namespace,
                created_at=failed_meeting.created_at,
                updated_at=failed_meeting.updated_at,
            )
            await publish_realtime_events(
                [event_call_transcript_failed(failed_payload, str(exc))]
            )
        raise


@broker.task
async def sync_summarize_transcript_task(meeting_id: str, company_id: str, actor_user_id: str) -> None:
    """Строит summary через Flows A2A skill и при необходимости запускает автоэкспорт в CRM."""
    logger.info(
        "sync_summarize_transcript_task start: meeting_id=%s company_id=%s actor=%s",
        meeting_id,
        company_id,
        actor_user_id,
    )
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    try:
        if meeting.transcript_text_file_id is None:
            raise ValueError(f"У встречи {meeting_id} отсутствует transcript_text_file_id.")
        transcript_file = await container.sync_file_repository.get(meeting.transcript_text_file_id)
        if transcript_file is None:
            raise ValueError(f"Файл {meeting.transcript_text_file_id} не найден.")

        settings = get_settings()
        flows_url = settings.server.get_flows_service_url()
        if not isinstance(flows_url, str) or flows_url == "":
            raise ValueError("service_urls.flows не задан.")
        flows_a2a_url = f"{flows_url.rstrip('/')}/flows/api/v1/crm"
        auth_headers = _build_interservice_auth_headers(
            actor_user_id=actor_user_id,
            company_id=company_id,
        )

        a2a_timeout_seconds = settings.summary_a2a_timeout_seconds
        if a2a_timeout_seconds <= 0:
            raise ValueError("summary_a2a_timeout_seconds должен быть больше 0.")
        a2a = A2AClient(timeout=a2a_timeout_seconds)
        response = await a2a.send_task(
            base_url=flows_a2a_url,
            skill_id="call_summary",
            content=(
                "Сформируй структурированное summary по встрече.\n"
                f"meeting_id={meeting.meeting_id}\n"
                f"transcript_ref={transcript_file.storage_url}"
            ),
            metadata={"meeting_id": meeting.meeting_id, "company_id": company_id},
            auth_headers=auth_headers,
        )
        logger.info(
            "sync_summarize_transcript_task a2a done: meeting_id=%s response_keys=%s",
            meeting.meeting_id,
            list(response.keys()),
        )

        summary = {
            "short_summary": response.get("response", ""),
            "decisions": [],
            "action_items": [],
            "open_questions": [],
            "risks": [],
        }
        await container.call_meeting_repository.update_summary(meeting.meeting_id, summary)
        after_summary = await container.call_meeting_repository.get(meeting.meeting_id)
        if after_summary is None:
            raise RuntimeError(f"Встреча {meeting.meeting_id} не найдена после summary.")
        auto_export_enabled = False
        if meeting.space_id is not None:
            space = await container.space_repository.get(meeting.space_id)
            if space is not None:
                auto_export_enabled = bool(space.auto_export_summary_to_crm or space.auto_export_transcript_to_crm)
        if not auto_export_enabled:
            await container.call_meeting_repository.set_export_status(
                meeting.meeting_id,
                status="done",
                target_namespace=after_summary.export_target_namespace,
            )
            after_summary = await container.call_meeting_repository.get(meeting.meeting_id)
            if after_summary is None:
                raise RuntimeError(f"Встреча {meeting.meeting_id} не найдена после обновления статуса.")
        summary_payload = CallMeetingRead(
            meeting_id=after_summary.meeting_id,
            call_id=after_summary.call_id,
            recording_id=after_summary.recording_id,
            channel_id=after_summary.channel_id,
            space_id=after_summary.space_id,
            transcript_file_id=after_summary.transcript_file_id,
            transcript_text_file_id=after_summary.transcript_text_file_id,
            summary_json=after_summary.summary_json or {},
            export_status=after_summary.export_status,
            export_target_namespace=after_summary.export_target_namespace,
            created_at=after_summary.created_at,
            updated_at=after_summary.updated_at,
        )
        await publish_realtime_events([event_call_summary_ready(summary_payload)])

        if auto_export_enabled:
            if meeting.space_id is None:
                raise ValueError("space_id обязателен для автоэкспорта встречи.")
            space = await container.space_repository.get(meeting.space_id)
            if space is None:
                raise ValueError(f"Пространство {meeting.space_id} не найдено для автоэкспорта встречи.")
            if space.namespace is None:
                raise ValueError("Для автоэкспорта встречи требуется namespace пространства.")
            await sync_export_meeting_to_crm_task.kiq(
                meeting_id=meeting.meeting_id,
                company_id=company_id,
                actor_user_id=actor_user_id,
                namespace=space.namespace,
            )
    except Exception as exc:
        logger.error(
            "sync_summarize_transcript_task failed: meeting_id=%s error=%s",
            meeting_id,
            str(exc),
            exc_info=True,
        )
        failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            await container.call_meeting_repository.set_export_status(
                failed_meeting.meeting_id,
                status="failed",
                target_namespace=failed_meeting.export_target_namespace,
            )
            failed_meeting = await container.call_meeting_repository.get(meeting_id)
        if failed_meeting is not None:
            failed_payload = CallMeetingRead(
                meeting_id=failed_meeting.meeting_id,
                call_id=failed_meeting.call_id,
                recording_id=failed_meeting.recording_id,
                channel_id=failed_meeting.channel_id,
                space_id=failed_meeting.space_id,
                transcript_file_id=failed_meeting.transcript_file_id,
                transcript_text_file_id=failed_meeting.transcript_text_file_id,
                summary_json=failed_meeting.summary_json or {},
                export_status=failed_meeting.export_status,
                export_target_namespace=failed_meeting.export_target_namespace,
                created_at=failed_meeting.created_at,
                updated_at=failed_meeting.updated_at,
            )
            await publish_realtime_events(
                [event_call_summary_failed(failed_payload, str(exc))]
            )
        raise


@broker.task
async def sync_export_meeting_to_crm_task(
    meeting_id: str,
    company_id: str,
    actor_user_id: str,
    namespace: str,
) -> None:
    """Экспортирует встречу в CRM как note:call."""
    if not isinstance(namespace, str) or namespace.strip() == "":
        raise ValueError("namespace обязателен.")
    container = get_sync_container()
    meeting = await container.call_meeting_repository.get(meeting_id)
    if meeting is None or meeting.company_id != company_id:
        raise ValueError(f"Встреча {meeting_id} не найдена.")
    recording = None
    if meeting.recording_id is not None:
        recording = await container.call_recording_repository.get(meeting.recording_id)
    call_participants = await container.call_repository.list_participants(meeting.call_id)
    registered_users: list[dict[str, str]] = []
    guests: list[dict[str, str]] = []
    for participant in call_participants:
        identity = participant.user_id
        if identity.startswith("guest:"):
            parts = identity.split(":", 2)
            guests.append(
                {
                    "guest_identity": identity,
                    "guest_name": parts[2] if len(parts) >= 3 else "guest",
                }
            )
        else:
            registered_users.append(
                {
                    "user_id": identity,
                    "display_name": identity,
                }
            )
    segments = await container.call_speaker_segment_repository.list_for_meeting(meeting.meeting_id, company_id)
    speaker_segments = [
        {
            "speaker_identity": s.speaker_identity,
            "speaker_type": s.speaker_type,
            "speaker_user_id": s.speaker_user_id,
            "speaker_guest_name": s.speaker_guest_name,
            "started_ms": s.started_ms,
            "ended_ms": s.ended_ms,
            "text": s.text,
        }
        for s in segments
    ]

    from core.clients import ServiceClient

    service_client = ServiceClient()
    auth_headers = _build_interservice_auth_headers(
        actor_user_id=actor_user_id,
        company_id=company_id,
    )
    payload = {
        "entity_type": "note",
        "entity_subtype": "call",
        "name": f"Встреча {meeting.meeting_id}",
        "description": "Автоматически экспортировано из Sync.",
        "namespace": namespace,
        "attributes": {
            "meeting_id": meeting.meeting_id,
            "call_id": meeting.call_id,
            "channel_id": meeting.channel_id,
            "space_id": meeting.space_id,
            "recording_id": meeting.recording_id,
            "raw_file_id": recording.raw_file_id if recording is not None else None,
            "transcript_file_id": meeting.transcript_file_id,
            "summary": meeting.summary_json,
            "participants": {
                "registered_users": registered_users,
                "guests": guests,
            },
            "speaker_segments": speaker_segments,
        },
    }
    try:
        await service_client.post(
            "crm",
            "/crm/api/v1/entities/",
            json=payload,
            headers=auth_headers,
        )
    except Exception:
        await container.call_meeting_repository.set_export_status(
            meeting.meeting_id,
            status="failed",
            target_namespace=namespace,
        )
        failed = await container.call_meeting_repository.get(meeting.meeting_id)
        if failed is None:
            raise RuntimeError("Встреча пропала после ошибки экспорта.")
        await publish_realtime_events(
            [
                event_call_export_crm_failed(
                    CallMeetingRead(
                        meeting_id=failed.meeting_id,
                        call_id=failed.call_id,
                        recording_id=failed.recording_id,
                        channel_id=failed.channel_id,
                        space_id=failed.space_id,
                        transcript_file_id=failed.transcript_file_id,
                        transcript_text_file_id=failed.transcript_text_file_id,
                        summary_json=failed.summary_json or {},
                        export_status=failed.export_status,
                        export_target_namespace=failed.export_target_namespace,
                        created_at=failed.created_at,
                        updated_at=failed.updated_at,
                    )
                )
            ]
        )
        raise
    await container.call_meeting_repository.set_export_status(
        meeting.meeting_id,
        status="done",
        target_namespace=namespace,
    )
    done = await container.call_meeting_repository.get(meeting.meeting_id)
    if done is None:
        raise RuntimeError("Встреча пропала после экспорта.")
    await publish_realtime_events(
        [
            event_call_export_crm_done(
                CallMeetingRead(
                    meeting_id=done.meeting_id,
                    call_id=done.call_id,
                    recording_id=done.recording_id,
                    channel_id=done.channel_id,
                    space_id=done.space_id,
                    transcript_file_id=done.transcript_file_id,
                    transcript_text_file_id=done.transcript_text_file_id,
                    summary_json=done.summary_json or {},
                    export_status=done.export_status,
                    export_target_namespace=done.export_target_namespace,
                    created_at=done.created_at,
                    updated_at=done.updated_at,
                )
            )
        ]
    )


@broker.task
async def sync_transcribe_audio_message_task(
    *,
    channel_id: str,
    message_id: str,
    company_id: str,
    actor_user_id: str,
) -> None:
    """Расшифровывает аудиосообщение и публикует обновление message.updated."""
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
    timeout_seconds = settings.stt.cloud_ru.timeout
    if timeout_seconds <= 0:
        raise ValueError("stt.cloud_ru.timeout должен быть больше 0.")

    sync_base_url = settings.server.get_service_url("sync")
    if not isinstance(sync_base_url, str) or sync_base_url == "":
        raise ValueError("URL sync сервиса не задан.")
    file_download_url = (
        f"{sync_base_url.rstrip('/')}/sync/api/v1/files/download/{audio_info.file_id}"
    )
    auth_headers = _build_interservice_auth_headers(
        actor_user_id=actor_user_id,
        company_id=company_id,
    )

    try:
        async with get_httpx_client(timeout=timeout_seconds) as client:
            response = await client.get(file_download_url, headers=auth_headers)
        response.raise_for_status()
        if not response.content:
            raise ValueError("Файл аудиосообщения пустой.")

        stt_client = STTClientFactory.create_client()
        transcript_result = await stt_client.transcribe_audio(
            audio_bytes=response.content,
            file_name=audio_info.filename,
            mime_type=audio_info.mime_type,
            language=settings.stt.cloud_ru.language,
        )
        if transcript_result.status != AudioTranscriptionStatus.DONE:
            raise ValueError(
                "STT вернул неуспешный статус транскрипции "
                f"для аудиосообщения {message_id}: {transcript_result.status.value}."
            )
        transcript_text = transcript_result.text
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
