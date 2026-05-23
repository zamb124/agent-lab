"""«Речь в ленту» на сервере: LiveKit segmented egress микрофона, опрос, сообщения в канал."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlparse
from uuid import uuid4

import aiohttp
import redis.asyncio as redis_async
from livekit.api import LiveKitAPI
from livekit.api.twirp_client import TwirpError, TwirpErrorCode
from livekit.protocol.models import TrackSource, TrackType
from livekit.protocol.room import ListParticipantsRequest

from apps.sync.container import get_sync_container
from apps.sync.db.models import SyncCallSpeechEgressTrack
from apps.sync.db.repositories.call_repository import CallNotFoundError
from apps.sync.models.messages import (
    MessageContentModel,
    MessageContentType,
    MessageCreate,
)
from apps.sync.realtime.handlers import send_message_with_side_effects
from core.calls.livekit_client import LiveKitClient
from core.calls.livekit_usage_spans import trace_livekit_egress_segmented_usage
from core.config import get_settings
from core.files.audio_probe import probe_audio_duration_ms_from_bytes
from core.files.audio_silence import (
    trim_leading_trailing_silence_from_bytes,
    volumedetect_max_volume_db_from_bytes,
)
from core.files.audio_transcode import transcode_audio_bytes_to_m4a_aac
from core.files.models import AudioAttachmentContent, AudioTranscriptionStatus
from core.files.processors import FileProcessor
from core.files.s3_client import S3ClientFactory
from core.http import get_httpx_client
from core.logging import get_logger
from core.models.identity_models import User

logger = get_logger(__name__)

_SPEECH_TO_CHAT_POLL_LOCK_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
else
  return 0
end
"""
_SPEECH_TO_CHAT_POLL_LOCK_EXTEND_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('expire', KEYS[1], tonumber(ARGV[2]))
else
  return 0
end
"""


@dataclass(frozen=True, slots=True)
class SpeechToChatPollOutcome:
    """Результат тика poll: нужно ли ставить следующий TaskIQ и с какой задержкой."""

    schedule_next: bool
    next_delay: Literal["normal", "lock_busy"] = "normal"


async def _stc_poll_lock_renew_loop(
    r: redis_async.Redis,
    lock_key: str,
    token: str,
    ttl_sec: int,
    interval_sec: float,
) -> None:
    try:
        while True:
            await asyncio.sleep(interval_sec)
            redis_eval = cast(Callable[..., Awaitable[Any]], r.eval)
            extended = await redis_eval(
                _SPEECH_TO_CHAT_POLL_LOCK_EXTEND_LUA,
                1,
                lock_key,
                token,
                str(ttl_sec),
            )
            if int(extended) != 1:
                logger.warning(
                    "speech_to_chat poll: не удалось продлить lock key=%s (возможно истёк TTL)",
                    lock_key,
                )
                break
    except asyncio.CancelledError:
        raise


def speech_to_chat_segment_seconds() -> int:
    """Длительность сегмента egress: `calls.speech_to_chat.segment_seconds` (conf.json / CALLS__SPEECH_TO_CHAT__*)."""
    return get_settings().calls.speech_to_chat.segment_seconds


def _livekit_http_base(ws_or_http_url: str) -> str:
    url = ws_or_http_url
    if url.startswith("ws://"):
        return "http://" + url[5:]
    if url.startswith("wss://"):
        return "https://" + url[6:]
    return url


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


def _content_type_for_segment_original_name(original_name: str) -> str:
    lower = original_name.lower()
    if lower.endswith(".aac"):
        return "audio/aac"
    if lower.endswith(".m4a") or lower.endswith(".mp4") or lower.endswith(".m4s"):
        return "audio/mp4"
    if lower.endswith(".ts"):
        return "video/mp2t"
    if lower.endswith(".opus") or lower.endswith(".ogg"):
        return "audio/ogg"
    if lower.endswith(".wav"):
        return "audio/wav"
    return "application/octet-stream"


_SPEECH_EGRESS_SEGMENT_SUFFIXES: tuple[str, ...] = (
    ".aac",
    ".m4a",
    ".m4s",
    ".opus",
    ".ogg",
    ".mp4",
    ".ts",
    ".wav",
)


def _speech_egress_s3_prefix(row: SyncCallSpeechEgressTrack) -> str:
    return (
        f"sync-speech/{row.company_id}/{row.call_id}/"
        f"{row.participant_identity}/{row.track_sid}/"
    )


def _file_entries_from_egress_info(egress_info: Any) -> list[tuple[str, str, int]]:
    entries: list[tuple[str, str, int]] = []
    for fr in egress_info.file_results:
        loc_raw = getattr(fr, "location", None)
        if loc_raw is None or loc_raw == "":
            continue
        if not isinstance(loc_raw, str):
            raise ValueError("LiveKit file_result.location должен быть строкой, если задан.")
        fn_raw = getattr(fr, "filename", None)
        if fn_raw is None:
            fn = "segment.bin"
        elif isinstance(fn_raw, str):
            fn = fn_raw if fn_raw != "" else "segment.bin"
        else:
            raise ValueError("LiveKit file_result.filename должен быть строкой или отсутствовать.")
        size_attr = getattr(fr, "size", 0)
        try:
            sz = int(size_attr or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"LiveKit file_result.size должен быть числом: {size_attr!r}") from exc
        entries.append((loc_raw, fn, sz))
    entries.sort(key=lambda x: x[1])
    return entries


async def _audio_segment_entries_from_s3_prefix(
    *,
    prefix: str,
    start_after_key: str | None,
    max_keys: int,
) -> list[tuple[str, str, int, str]]:
    """Сегменты под префиксом egress; пачка с StartAfter — без повторного чтения уже обработанных ключей."""
    settings = get_settings()
    if not settings.s3.enabled:
        return []
    default_key = settings.s3.default_bucket
    if default_key == "" or default_key not in settings.s3.buckets:
        raise ValueError("s3.default_bucket не настроен для speech-to-chat.")
    client = S3ClientFactory.create_client_for_bucket(default_key)
    listed = await client.list_objects(
        prefix=prefix,
        max_keys=max_keys,
        start_after=start_after_key,
    )
    entries: list[tuple[str, str, int, str]] = []
    for obj in sorted(listed, key=lambda x: x["key"]):
        key = obj["key"]
        lower = key.lower()
        if lower.endswith(".m3u8"):
            continue
        if not any(lower.endswith(suf) for suf in _SPEECH_EGRESS_SEGMENT_SUFFIXES):
            continue
        name = key.rsplit("/", 1)[-1]
        if name == "":
            continue
        url = client.get_public_url(key)
        entries.append((url, name, int(obj["size"]), key))
    return entries


async def _find_egress_info(
    livekit_client: LiveKitClient,
    *,
    room_name: str,
    egress_id: str,
    api: LiveKitAPI | None = None,
) -> Any | None:
    items = await livekit_client.list_egress(room_name=room_name, active=None, api=api)
    for it in items:
        eid = getattr(it, "egress_id", None)
        if isinstance(eid, str) and eid == egress_id:
            return it
    return None


async def _http_get_segment_bytes(url: str) -> bytes:
    timeout = get_settings().calls.speech_to_chat.segment_http_download_timeout_seconds
    async with get_httpx_client(timeout=timeout) as client:
        response = await client.get(url)
        response.raise_for_status()
        body = response.content
    if not body:
        raise ValueError("Пустой ответ при загрузке сегмента speech-to-chat.")
    return body


async def _fetch_segment_bytes(*, storage_url: str) -> bytes:
    """
    Сегменты лежат в default S3 bucket; публичный URL часто без анонимного чтения (403).
    Сначала path-style URL `{endpoint}/{bucket}/{key}` — чтение через SDK с ключами из конфига.
    """
    settings = get_settings()
    parsed = urlparse(storage_url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Некорректный URL сегмента speech-to-chat: {storage_url}")
    path = parsed.path.lstrip("/")
    if "/" in path and settings.s3.enabled and settings.s3.default_bucket != "":
        bucket_part, _, object_key = path.partition("/")
        if object_key != "":
            default_key = settings.s3.default_bucket
            if default_key in settings.s3.buckets:
                bconf = settings.s3.buckets[default_key]
                physical = bconf.bucket_name or default_key
                if bucket_part == physical or bucket_part == default_key:
                    client = S3ClientFactory.create_client_for_bucket(default_key)
                    try:
                        return await client.download_bytes(object_key)
                    finally:
                        await client.close()
    return await _http_get_segment_bytes(storage_url)


async def _normalize_egress_audio_for_upload_pipeline(
    data: bytes, *, original_name: str, content_type: str
) -> tuple[bytes, str, str]:
    """
    Форматы сегментов egress (ADTS AAC, MPEG-TS, fMP4 .m4s) приводим к M4A+faststart,
    как после перекодирования в обычной загрузке голосового для Safari.
    Остальное оставляем — дальше тот же FileProcessor, что и POST .../files/.
    """
    base_content_type = content_type.split(";")[0].strip().lower()
    suf = Path(original_name).suffix.lower()
    needs_m4a = suf in (".aac", ".m4s", ".ts") or base_content_type in (
        "audio/aac",
        "video/mp2t",
    )
    if base_content_type == "audio/mp4" and suf == ".m4s":
        needs_m4a = True
    if base_content_type == "application/octet-stream" and suf in (".aac", ".m4s", ".ts"):
        needs_m4a = True
    if not needs_m4a:
        return data, original_name, content_type
    src_suffix = suf if suf else ".aac"
    out = await transcode_audio_bytes_to_m4a_aac(data, src_suffix)
    stem = Path(original_name).stem
    if stem == "" or stem == ".":
        stem = "segment"
    return out, f"{stem}.m4a", "audio/mp4"


async def _post_segment_file_as_message(
    *,
    row: SyncCallSpeechEgressTrack,
    storage_url: str,
    original_name: str,
    file_size: int,
    content_type: str,
    call_id: str,
) -> None:
    settings = get_settings()
    if not settings.s3.enabled or settings.s3.default_bucket == "":
        raise ValueError("S3 не настроен: speech-to-chat не может сохранить сегмент как файл канала.")

    normalized_url = _normalize_storage_url_for_worker(
        storage_url=storage_url,
        testing=bool(getattr(settings, "testing", False)),
    )
    raw = await _fetch_segment_bytes(storage_url=normalized_url)
    if file_size > 0 and len(raw) != file_size:
        raise ValueError(
            f"Размер сегмента не совпадает с ожидаемым: got={len(raw)} expected={file_size} url={normalized_url}"
        )

    normalized_audio, upload_name, upload_mime = await _normalize_egress_audio_for_upload_pipeline(
        raw, original_name=original_name, content_type=content_type
    )

    stc = settings.calls.speech_to_chat
    upload_suffix = Path(upload_name).suffix.lower() or ".bin"
    base_upload_mime = upload_mime.split(";")[0].strip().lower()
    if base_upload_mime.startswith("audio/"):
        max_vol_db = await volumedetect_max_volume_db_from_bytes(
            normalized_audio, upload_suffix
        )
        if max_vol_db < stc.speech_segment_discard_below_max_volume_db:
            logger.info(
                "speech_to_chat: сегмент без существенного сигнала call_id=%s track=%s max_volume_db=%s",
                call_id,
                row.track_sid,
                max_vol_db,
            )
            return
        normalized_audio = await trim_leading_trailing_silence_from_bytes(
            normalized_audio,
            source_suffix=upload_suffix,
            threshold_db=stc.speech_segment_trim_silence_threshold_db,
            min_silence_sec=stc.speech_segment_trim_min_silence_sec,
        )
        duration_ms = await probe_audio_duration_ms_from_bytes(
            normalized_audio, upload_suffix
        )
        if duration_ms < stc.speech_segment_min_post_duration_ms:
            logger.info(
                "speech_to_chat: после обрезки тишины сегмент слишком короткий call_id=%s track=%s duration_ms=%s",
                call_id,
                row.track_sid,
                duration_ms,
            )
            return
    else:
        duration_ms = await probe_audio_duration_ms_from_bytes(
            normalized_audio, upload_suffix
        )
    if duration_ms <= 0:
        raise ValueError("Не удалось определить длительность сегмента speech-to-chat.")

    checksum = hashlib.sha256(normalized_audio).hexdigest()
    container = get_sync_container()
    processor = FileProcessor(file_repository=container.file_repository)
    try:
        api_prefix = f"/{settings.server.name}/api/v1"
        download_url_prefix = f"{api_prefix}/files/download"
        file_record = await processor.persist_uploaded_file(
            data=normalized_audio,
            original_name=upload_name,
            content_type=upload_mime,
            uploaded_by=row.participant_identity,
            company_id=row.company_id,
            public=True,
            download_url_prefix=download_url_prefix,
            content_sha256_hex=checksum,
        )
    finally:
        await processor.close()

    body = MessageCreate(
        thread_id=None,
        parent_message_id=None,
        contents=[
            MessageContentModel(
                type=MessageContentType.FILE_AUDIO,
                data=AudioAttachmentContent(
                    file_id=file_record.file_id,
                    original_name=file_record.original_name,
                    content_type=file_record.content_type,
                    file_size=file_record.file_size,
                    duration_ms=duration_ms,
                    waveform=None,
                    transcription_status=AudioTranscriptionStatus.IDLE,
                    transcription_text=None,
                    transcription_error=None,
                    source_speech_to_chat=True,
                ),
                order=0,
            )
        ],
        mentioned_user_ids=None,
        call_id=call_id,
    )
    user = User(
        user_id=row.participant_identity,
        name=row.participant_identity,
        active_company_id=row.company_id,
    )
    await send_message_with_side_effects(
        channel_id=row.channel_id,
        body=body,
        user=user,
        container=get_sync_container(),
    )


async def process_new_files_for_egress_row(
    *,
    row: SyncCallSpeechEgressTrack,
    egress_info: Any,
    call_id: str,
) -> None:
    container = get_sync_container()
    repo = container.call_speech_egress_track_repository
    budget = get_settings().calls.speech_to_chat.max_segments_per_poll_per_track

    livekit_entries = _file_entries_from_egress_info(egress_info)
    if len(livekit_entries) > 0:
        while budget > 0:
            fresh = await repo.get_by_call_and_track(call_id, row.track_sid)
            if fresh is None:
                return
            if fresh.segments_posted >= len(livekit_entries):
                return
            idx = fresh.segments_posted
            loc, fn, sz = livekit_entries[idx]
            content_type = _content_type_for_segment_original_name(fn)
            await _post_segment_file_as_message(
                row=fresh,
                storage_url=loc,
                original_name=fn,
                file_size=sz,
                content_type=content_type,
                call_id=call_id,
            )
            segment_s3_key = f"{_speech_egress_s3_prefix(fresh)}{fn}"
            await repo.set_segments_posted(
                fresh.row_id,
                idx + 1,
                last_segment_s3_key=segment_s3_key,
            )
            budget -= 1
        return

    prefix = _speech_egress_s3_prefix(row)
    page_size = get_settings().calls.speech_to_chat.s3_segment_list_page_size
    while budget > 0:
        fresh = await repo.get_by_call_and_track(call_id, row.track_sid)
        if fresh is None:
            return
        page = await _audio_segment_entries_from_s3_prefix(
            prefix=prefix,
            start_after_key=fresh.last_segment_s3_key,
            max_keys=page_size,
        )
        if len(page) == 0:
            return
        n = fresh.segments_posted
        last_obj_key: str | None = None
        for loc, fn, sz, obj_key in page:
            if budget <= 0:
                break
            content_type = _content_type_for_segment_original_name(fn)
            await _post_segment_file_as_message(
                row=fresh,
                storage_url=loc,
                original_name=fn,
                file_size=sz,
                content_type=content_type,
                call_id=call_id,
            )
            n += 1
            last_obj_key = obj_key
            budget -= 1
        if last_obj_key is None:
            return
        await repo.set_segments_posted(
            fresh.row_id, n, last_segment_s3_key=last_obj_key
        )
        if len(page) < page_size:
            return


def _s3_params_from_settings() -> tuple[str, str, str, str, str | None]:
    settings = get_settings()
    if not settings.s3.enabled:
        raise ValueError("S3 отключен: speech-to-chat egress в S3 недоступен.")
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

    endpoint_raw = bucket_config.endpoint_url
    ep: str | None = None
    if endpoint_raw is not None and endpoint_raw.strip() != "":
        trimmed = endpoint_raw.strip()
        parsed = urlparse(trimmed)
        if parsed.scheme == "":
            ep = trimmed
        elif parsed.netloc == "":
            raise ValueError(f"Некорректный endpoint_url для S3 egress: {endpoint_raw}")
        else:
            hostname = parsed.hostname
            if hostname is None or hostname == "":
                raise ValueError(f"Некорректный hostname в endpoint_url для S3 egress: {endpoint_raw}")
            if hostname == "localhost" or hostname == "127.0.0.1":
                hostname = "host.docker.internal"
            if parsed.port is None:
                netloc = hostname
            else:
                netloc = f"{hostname}:{parsed.port}"
            ep = f"{parsed.scheme}://{netloc}"
    return (
        bucket_config.access_key_id,
        bucket_config.secret_access_key,
        bucket_config.region_name,
        real_bucket_name,
        ep,
    )


async def run_speech_to_chat_poll_cycle(
    *, call_id: str, company_id: str
) -> SpeechToChatPollOutcome:
    """Определяет, ставить ли следующий тик TaskIQ и с обычной или увеличенной задержкой."""
    container = get_sync_container()
    try:
        call = await container.call_repository.get_call(call_id, company_id)
    except CallNotFoundError:
        return SpeechToChatPollOutcome(schedule_next=False)

    if call.status != "active":
        return SpeechToChatPollOutcome(schedule_next=False)
    if call.livekit_room_name is None or call.livekit_room_name == "":
        return SpeechToChatPollOutcome(schedule_next=False)

    channel_entity = await container.channel_repository.get(call.channel_id)
    if channel_entity is None:
        raise ValueError(f"Канал {call.channel_id} не найден.")
    if channel_entity.company_id != company_id:
        raise ValueError(f"Канал {call.channel_id} не принадлежит компании.")
    if not channel_entity.speech_to_chat_enabled:
        return SpeechToChatPollOutcome(schedule_next=False)

    settings = get_settings()
    stc = settings.calls.speech_to_chat
    redis_url = settings.database.redis_url
    if redis_url is None or redis_url.strip() == "":
        raise ValueError("database.redis_url обязателен для speech-to-chat poll (single-flight).")

    r = redis_async.from_url(redis_url)
    lock_key = f"sync:stc_poll:{company_id}:{call_id}"
    token = uuid4().hex
    renew_task: asyncio.Task[None] | None = None
    try:
        acquired = await r.set(
            lock_key,
            token,
            nx=True,
            ex=stc.poll_lock_ttl_seconds,
        )
        if not acquired:
            logger.debug(
                "speech_to_chat poll пропуск: lock занят call_id=%s company=%s",
                call_id,
                company_id,
            )
            return SpeechToChatPollOutcome(
                schedule_next=True,
                next_delay="lock_busy",
            )
        renew_task = asyncio.create_task(
            _stc_poll_lock_renew_loop(
                r,
                lock_key,
                token,
                stc.poll_lock_ttl_seconds,
                stc.poll_lock_refresh_interval_seconds,
            ),
        )
        inner_continue = await _run_speech_to_chat_poll_cycle_inner(
            call_id=call_id, company_id=company_id
        )
        return SpeechToChatPollOutcome(
            schedule_next=inner_continue,
            next_delay="normal",
        )
    finally:
        if renew_task is not None:
            renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await renew_task
        redis_eval = cast(Callable[..., Awaitable[Any]], r.eval)
        await redis_eval(_SPEECH_TO_CHAT_POLL_LOCK_RELEASE_LUA, 1, lock_key, token)
        await r.aclose()


async def _run_speech_to_chat_poll_cycle_inner(*, call_id: str, company_id: str) -> bool:
    container = get_sync_container()
    call = await container.call_repository.get_call(call_id, company_id)
    if call.status != "active":
        return False
    if call.livekit_room_name is None or call.livekit_room_name == "":
        return False

    channel_entity = await container.channel_repository.get(call.channel_id)
    if channel_entity is None:
        raise ValueError(f"Канал {call.channel_id} не найден.")
    if channel_entity.company_id != company_id:
        raise ValueError(f"Канал {call.channel_id} не принадлежит компании.")
    if not channel_entity.speech_to_chat_enabled:
        return False

    settings = get_settings()
    try:
        ak, sk, region, bucket, endpoint = _s3_params_from_settings()
    except ValueError as exc:
        logger.error("speech_to_chat: %s", str(exc))
        return False

    lk = LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )
    room_name = call.livekit_room_name
    base_http = _livekit_http_base(settings.calls.livekit_url)
    lk_timeout = settings.calls.speech_to_chat.livekit_client_timeout_seconds
    poll_timeout = aiohttp.ClientTimeout(total=lk_timeout)
    try:
        async with aiohttp.ClientSession(timeout=poll_timeout) as http_session:
            async with LiveKitAPI(
                base_http,
                settings.calls.livekit_api_key,
                settings.calls.livekit_api_secret,
                session=http_session,
            ) as api:
                try:
                    res = await api.room.list_participants(ListParticipantsRequest(room=room_name))
                except TimeoutError:
                    logger.warning("speech_to_chat: list_participants timed out room=%s", room_name)
                    return True
                participants = list(res.participants)

                speech_repo = container.call_speech_egress_track_repository
                for participant in participants:
                    identity = getattr(participant, "identity", "") or ""
                    if identity == "":
                        continue
                    for track in participant.tracks:
                        if track.type != TrackType.AUDIO:
                            continue
                        if track.source not in (TrackSource.MICROPHONE, TrackSource.UNKNOWN):
                            continue
                        track_sid = getattr(track, "sid", "") or ""
                        if track_sid == "":
                            continue
                        existing = await speech_repo.get_by_call_and_track(call_id, track_sid)
                        if existing is not None:
                            continue
                        prefix = f"sync-speech/{company_id}/{call_id}/{identity}/{track_sid}/"
                        try:
                            egress_info = await lk.start_track_composite_segmented_audio_to_s3(
                                room_name=room_name,
                                audio_track_id=track_sid,
                                filepath_prefix=prefix,
                                segment_duration_seconds=speech_to_chat_segment_seconds(),
                                s3_access_key=ak,
                                s3_secret_key=sk,
                                s3_region=region,
                                s3_bucket=bucket,
                                company_id=company_id,
                                user_id=identity,
                                s3_endpoint=endpoint,
                                api=api,
                            )
                        except TwirpError as exc:
                            logger.warning(
                                "speech_to_chat: не удалось стартовать egress track=%s call=%s: %s",
                                track_sid,
                                call_id,
                                str(exc),
                            )
                            continue
                        egress_id = getattr(egress_info, "egress_id", None)
                        if not isinstance(egress_id, str) or egress_id == "":
                            raise RuntimeError("LiveKit не вернул egress_id для speech-to-chat.")
                        row = SyncCallSpeechEgressTrack(
                            row_id=uuid4().hex,
                            call_id=call_id,
                            company_id=company_id,
                            channel_id=call.channel_id,
                            participant_identity=identity,
                            track_sid=track_sid,
                            egress_id=egress_id,
                            segments_posted=0,
                        )
                        await speech_repo.create(row)
                        logger.info(
                            "speech_to_chat egress started: call_id=%s identity=%s track=%s egress_id=%s",
                            call_id,
                            identity,
                            track_sid,
                            egress_id,
                        )

                rows = await speech_repo.list_for_call(call_id, company_id)
                for row in rows:
                    info = await _find_egress_info(
                        lk, room_name=room_name, egress_id=row.egress_id, api=api
                    )
                    if info is None:
                        continue
                    await process_new_files_for_egress_row(
                        row=row, egress_info=info, call_id=call_id
                    )
    except TimeoutError:
        logger.warning("speech_to_chat: LiveKit запрос превысил таймаут room=%s", room_name)
        return True

    return True


async def stop_speech_egresses_for_call_room(
    *,
    call_id: str,
    company_id: str,
    room_name: str,
    actor_user_id: str,
) -> None:
    container = get_sync_container()
    repo = container.call_speech_egress_track_repository
    rows = await repo.list_for_call(call_id, company_id)
    if len(rows) == 0:
        return
    if actor_user_id.strip() == "":
        raise ValueError("actor_user_id обязателен для stop_speech_egresses_for_call_room.")

    settings = get_settings()
    lk = LiveKitClient(
        url=settings.calls.livekit_url,
        api_key=settings.calls.livekit_api_key,
        api_secret=settings.calls.livekit_api_secret,
    )
    base_http = _livekit_http_base(settings.calls.livekit_url)
    lk_timeout = settings.calls.speech_to_chat.livekit_client_timeout_seconds
    stop_timeout = aiohttp.ClientTimeout(total=lk_timeout)
    async with aiohttp.ClientSession(timeout=stop_timeout) as http_session:
        async with LiveKitAPI(
            base_http,
            settings.calls.livekit_api_key,
            settings.calls.livekit_api_secret,
            session=http_session,
        ) as api:
            for row in rows:
                info: Any | None = None
                try:
                    info = await lk.stop_egress(
                        egress_id=row.egress_id,
                        company_id=company_id,
                        user_id=actor_user_id,
                        api=api,
                    )
                except TwirpError as exc:
                    if exc.code in (TwirpErrorCode.NOT_FOUND, TwirpErrorCode.FAILED_PRECONDITION):
                        logger.warning(
                            "speech_to_chat egress stop skipped (already done): call_id=%s egress_id=%s",
                            call_id,
                            row.egress_id,
                        )
                    else:
                        raise
                if info is None:
                    info = await _find_egress_info(
                        lk, room_name=room_name, egress_id=row.egress_id, api=api
                    )
                if info is not None:
                    await process_new_files_for_egress_row(
                        row=row, egress_info=info, call_id=call_id
                    )

    now = datetime.now(UTC)
    total_track_minutes = 0
    for row in rows:
        secs = (now - row.created_at).total_seconds()
        if secs > 0:
            total_track_minutes += max(1, int(math.ceil(secs / 60.0)))
    if total_track_minutes > 0:
        call_entity = await container.call_repository.get_call(call_id, company_id)
        await trace_livekit_egress_segmented_usage(
            company_id=company_id,
            user_id=call_entity.created_by_user_id,
            call_id=call_id,
            livekit_room_name=room_name,
            billed_minutes=total_track_minutes,
        )

    await repo.delete_for_call(call_id, company_id)
    logger.info(
        "speech_to_chat egress очищено: call_id=%s room=%s rows=%s",
        call_id,
        room_name,
        len(rows),
    )
