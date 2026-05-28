"""Чанкование аудио через ffmpeg и STT-транскрипция с автоматическим разбиением."""

import asyncio
import subprocess
import tempfile
from pathlib import Path

import httpx

from core.clients.speech_override import SpeechOverride
from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.clients.voice_resolver import get_stt_client
from core.config import get_settings
from core.files.models import AudioTranscriptionStatus
from core.logging import get_logger

logger = get_logger(__name__)


def _normalize_content_type(raw_content_type: str | None) -> str | None:
    if raw_content_type is None:
        return None
    if raw_content_type == "":
        return None
    return raw_content_type.split(";", 1)[0].strip().lower()


def audio_needs_mp3_upload_for_stt(*, file_name: str, content_type: str) -> bool:
    """Контейнеры вроде M4A/MP4: cloud.ru STT в multipart часто отвечает Format not recognised.

    Для них сначала гоняем байты через ffmpeg в MP3 (как при чанковании).
    """
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix in ("m4a", "mp4", "mov", "3gp"):
        return True
    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type is None:
        return False
    return normalized_content_type in (
        "audio/mp4",
        "audio/x-m4a",
        "video/mp4",
        "video/quicktime",
    )


def normalize_audio_to_mp3_for_stt(
    *,
    audio_bytes: bytes,
    file_name: str,
    content_type: str,
    chunk_bitrate_kbps: int,
    chunk_sample_rate_hz: int,
    chunk_channels: int,
) -> tuple[bytes, str]:
    """Одна дорожка → MP3 теми же параметрами, что и сегменты `split_audio_for_stt_chunks`."""
    if not audio_bytes:
        raise ValueError("audio_bytes не может быть пустым.")
    if chunk_bitrate_kbps <= 0:
        raise ValueError("chunk_bitrate_kbps должен быть больше 0.")
    if chunk_sample_rate_hz <= 0:
        raise ValueError("chunk_sample_rate_hz должен быть больше 0.")
    if chunk_channels <= 0:
        raise ValueError("chunk_channels должен быть больше 0.")

    input_extension = _audio_input_extension(file_name=file_name, content_type=content_type)
    file_stem = Path(file_name).stem
    if file_stem == "":
        file_stem = "recording"
    out_file_name = f"{file_stem}.mp3"

    with tempfile.TemporaryDirectory(prefix="media-stt-norm-") as work_dir:
        source_path = Path(work_dir) / f"source.{input_extension}"
        _ = source_path.write_bytes(audio_bytes)
        out_path = Path(work_dir) / "normalized.mp3"
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
            message = (
                "Не удалось нормализовать аудио в MP3 для STT. "
                + f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
            raise RuntimeError(message)
        mp3_bytes = out_path.read_bytes()
        if len(mp3_bytes) == 0:
            raise ValueError("Нормализация STT дала пустой MP3.")
        return mp3_bytes, out_file_name


def _audio_input_extension(file_name: str, content_type: str) -> str:
    if file_name == "":
        raise ValueError("file_name не может быть пустым.")
    if content_type == "":
        raise ValueError("content_type не может быть пустым.")
    suffix = Path(file_name).suffix.lower().lstrip(".")
    if suffix != "":
        return suffix
    normalized_content_type = _normalize_content_type(content_type)
    if normalized_content_type is None:
        return "bin"
    if "/" not in normalized_content_type:
        return "bin"
    subtype = normalized_content_type.split("/", 1)[1]
    subtype_map = {
        "x-m4a": "m4a",
        "mpeg": "mp3",
    }
    return subtype_map.get(subtype, subtype)


def validate_stt_result_text(
    *,
    transcript_result: STTTranscriptionResult,
    job_id: str,
    context: str,
) -> str:
    """Проверяет, что STT вернул успешный непустой результат."""
    if transcript_result.status != AudioTranscriptionStatus.DONE:
        message = (
            "STT вернул неуспешный статус транскрипции "
            + f"для job_id={job_id}: {transcript_result.status.value}. context={context}"
        )
        raise ValueError(message)
    transcript_text = transcript_result.text
    if transcript_text.strip() == "":
        raise ValueError(f"STT вернул пустую транскрипцию для job_id={job_id}. context={context}")
    return transcript_text


def is_stt_format_not_recognized_error(error: Exception) -> bool:
    """Определяет, является ли ошибка STT ошибкой формата (нужно перекодирование)."""
    message = str(error).lower()
    return (
        "format not recognised" in message
        or "format not recognized" in message
        or "error opening <_io.bytesio object>" in message
    )


def split_audio_for_stt_chunks(
    *,
    audio_bytes: bytes,
    file_name: str,
    content_type: str,
    max_upload_bytes: int,
    chunk_duration_seconds: int,
    chunk_bitrate_kbps: int,
    chunk_sample_rate_hz: int,
    chunk_channels: int,
) -> list[tuple[str, bytes, str]]:
    """Разбивает аудиофайл на чанки через ffmpeg для порционной STT-транскрипции.

    Возвращает:
        Список кортежей (file_name, bytes, content_type) по одному на чанк.
    """
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

    input_extension = _audio_input_extension(file_name=file_name, content_type=content_type)
    file_stem = Path(file_name).stem
    if file_stem == "":
        file_stem = "recording"

    chunks: list[tuple[str, bytes, str]] = []
    with tempfile.TemporaryDirectory(prefix="media-stt-chunks-") as work_dir:
        source_path = Path(work_dir) / f"source.{input_extension}"
        _ = source_path.write_bytes(audio_bytes)
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
            message = (
                "Не удалось подготовить аудио чанки для STT через ffmpeg. "
                + f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
            raise RuntimeError(message)
        segment_files = sorted(Path(work_dir).glob("segment-*.mp3"))
        if len(segment_files) == 0:
            raise RuntimeError("ffmpeg не сформировал ни одного STT чанка.")
        for chunk_index, segment_file in enumerate(segment_files, start=1):
            chunk_bytes = segment_file.read_bytes()
            if len(chunk_bytes) == 0:
                raise ValueError(f"STT chunk #{chunk_index} получился пустым.")
            if len(chunk_bytes) > max_upload_bytes:
                message = (
                    "STT chunk превышает допустимый размер upload. "
                    + f"chunk_index={chunk_index} size={len(chunk_bytes)} max={max_upload_bytes}. "
                    + "Уменьшите media_transcriber.chunk_duration_seconds или chunk_bitrate_kbps."
                )
                raise ValueError(message)
            chunk_file_name = f"{file_stem}-part-{chunk_index:04d}.mp3"
            chunks.append((chunk_file_name, chunk_bytes, "audio/mpeg"))
    if len(chunks) == 0:
        raise ValueError("Не удалось сформировать чанки для STT.")
    return chunks


async def transcribe_audio_with_chunking(
    *,
    job_id: str,
    company_id: str,
    audio_bytes: bytes,
    file_name: str,
    content_type: str,
    language: str | None = None,
    speech_override: SpeechOverride | None = None,
    stt_client: BaseSTTClient | None = None,
) -> tuple[str, str]:
    """Транскрибирует аудио через STT с автоматическим чанкованием при необходимости.

    Сначала пробует одним запросом. Если файл слишком большой (413) или формат
    не распознан, разбивает на чанки через ffmpeg и транскрибирует каждый.

    Аргументы:
        job_id: идентификатор задачи для логирования
        company_id: идентификатор компании для tier-резолва STT
        audio_bytes: байты аудиофайла
        file_name: имя файла
        content_type: платформенный MIME-тип файла (``audio/wav`` и т.п.)
        language: язык (если None — см. tier-резолв и media_transcriber.default_language)
        speech_override: необязательный per-call override провайдера/модели
        stt_client: инъекция клиента для тестов (если None — ``get_stt_client``)

    Возвращает:
        Кортеж (полный текст, идентификатор провайдера из последнего ответа STT).
    """
    if company_id == "":
        raise ValueError("company_id обязателен для transcribe_audio_with_chunking.")

    settings = get_settings()
    mt = settings.media_transcriber
    max_upload_bytes = mt.chunk_max_upload_bytes
    chunk_duration_seconds = mt.chunk_duration_seconds
    chunk_bitrate_kbps = mt.chunk_bitrate_kbps
    chunk_sample_rate_hz = mt.chunk_sample_rate_hz
    chunk_channels = mt.chunk_channels

    if stt_client is None:
        stt_client = await get_stt_client(
            company_id=company_id, override=speech_override
        )

    last_provider = ""

    should_chunk_first = len(audio_bytes) > max_upload_bytes

    async def _single_shot(
        payload_bytes: bytes,
        payload_name: str,
        payload_content_type: str,
        *,
        context: str,
    ) -> str:
        nonlocal last_provider
        transcript_result = await stt_client.transcribe_audio(
            audio_bytes=payload_bytes,
            file_name=payload_name,
            content_type=payload_content_type,
            language=language,
        )
        last_provider = transcript_result.provider
        return validate_stt_result_text(
            transcript_result=transcript_result,
            job_id=job_id,
            context=context,
        )

    if not should_chunk_first:
        if audio_needs_mp3_upload_for_stt(file_name=file_name, content_type=content_type):
            norm_bytes, norm_name = await asyncio.to_thread(
                normalize_audio_to_mp3_for_stt,
                audio_bytes=audio_bytes,
                file_name=file_name,
                content_type=content_type,
                chunk_bitrate_kbps=chunk_bitrate_kbps,
                chunk_sample_rate_hz=chunk_sample_rate_hz,
                chunk_channels=chunk_channels,
            )
            if len(norm_bytes) <= max_upload_bytes:
                try:
                    text = await _single_shot(
                        norm_bytes,
                        norm_name,
                        "audio/mpeg",
                        context="single_request_mp3_normalized",
                    )
                    return text, last_provider
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 413:
                        raise
                    logger.warning(
                        "STT normalized single request returned 413; switching to chunked mode: "
                        + "job_id=%s file=%s bytes=%s",
                        job_id,
                        file_name,
                        len(audio_bytes),
                    )
                except ValueError as exc:
                    if not is_stt_format_not_recognized_error(exc):
                        raise
                    logger.warning(
                        "STT normalized single request returned format error; switching to chunked mode: "
                        + "job_id=%s file=%s error=%s",
                        job_id,
                        file_name,
                        str(exc),
                    )
        else:
            try:
                text = await _single_shot(
                    audio_bytes,
                    file_name,
                    content_type,
                    context="single_request",
                )
                return text, last_provider
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
                if not is_stt_format_not_recognized_error(exc):
                    raise
                logger.warning(
                    "STT single request returned format error; switching to chunked mode: "
                    + "job_id=%s file=%s content_type=%s error=%s",
                    job_id,
                    file_name,
                    content_type,
                    str(exc),
                )

    chunks = await asyncio.to_thread(
        split_audio_for_stt_chunks,
        audio_bytes=audio_bytes,
        file_name=file_name,
        content_type=content_type,
        max_upload_bytes=max_upload_bytes,
        chunk_duration_seconds=chunk_duration_seconds,
        chunk_bitrate_kbps=chunk_bitrate_kbps,
        chunk_sample_rate_hz=chunk_sample_rate_hz,
        chunk_channels=chunk_channels,
    )
    chunk_texts: list[str] = []
    for index, (chunk_file_name, chunk_bytes, chunk_content_type) in enumerate(chunks, start=1):
        transcript_result = await stt_client.transcribe_audio(
            audio_bytes=chunk_bytes,
            file_name=chunk_file_name,
            content_type=chunk_content_type,
            language=language,
        )
        last_provider = transcript_result.provider
        chunk_text = validate_stt_result_text(
            transcript_result=transcript_result,
            job_id=job_id,
            context=f"chunk_{index}",
        ).strip()
        if chunk_text != "":
            chunk_texts.append(chunk_text)
    if len(chunk_texts) == 0:
        raise ValueError(f"STT вернул пустые транскрипции для всех чанков job_id={job_id}.")
    if last_provider == "":
        raise ValueError("STT не вернул идентификатор провайдера (last_provider пуст).")
    return "\n".join(chunk_texts), last_provider
