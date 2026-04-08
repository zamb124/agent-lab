"""Чанкование аудио через ffmpeg и STT-транскрипция с автоматическим разбиением."""

import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import httpx

from core.clients.stt_client import BaseSTTClient, STTClientFactory
from core.config import get_settings
from core.files.models import AudioTranscriptionStatus

logger = logging.getLogger(__name__)


def _normalize_mime_type(raw_mime_type: str | None) -> str | None:
    if raw_mime_type is None:
        return None
    if raw_mime_type == "":
        return None
    return raw_mime_type.split(";", 1)[0].strip().lower()


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


def validate_stt_result_text(
    *,
    transcript_result: Any,
    job_id: str,
    context: str,
) -> str:
    """Проверяет, что STT вернул успешный непустой результат."""
    if transcript_result.status != AudioTranscriptionStatus.DONE:
        raise ValueError(
            "STT вернул неуспешный статус транскрипции "
            f"для job_id={job_id}: {transcript_result.status.value}. context={context}"
        )
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
    mime_type: str,
    max_upload_bytes: int,
    chunk_duration_seconds: int,
    chunk_bitrate_kbps: int,
    chunk_sample_rate_hz: int,
    chunk_channels: int,
) -> list[tuple[str, bytes, str]]:
    """Разбивает аудиофайл на чанки через ffmpeg для порционной STT-транскрипции.

    Returns:
        Список кортежей (file_name, bytes, mime_type) по одному на чанк.
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

    input_extension = _audio_input_extension(file_name=file_name, mime_type=mime_type)
    file_stem = Path(file_name).stem
    if file_stem == "":
        file_stem = "recording"

    chunks: list[tuple[str, bytes, str]] = []
    with tempfile.TemporaryDirectory(prefix="media-stt-chunks-") as work_dir:
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


async def transcribe_audio_with_chunking(
    *,
    job_id: str,
    audio_bytes: bytes,
    file_name: str,
    mime_type: str,
    language: str | None = None,
    stt_client: BaseSTTClient | None = None,
) -> str:
    """Транскрибирует аудио через STT с автоматическим чанкованием при необходимости.

    Сначала пробует одним запросом. Если файл слишком большой (413) или формат
    не распознан, разбивает на чанки через ffmpeg и транскрибирует каждый.

    Args:
        job_id: идентификатор задачи для логирования
        audio_bytes: байты аудиофайла
        file_name: имя файла
        mime_type: MIME-тип
        language: язык (если None — дефолтный из конфига STT)
        stt_client: клиент STT (если None — создаётся через STTClientFactory)

    Returns:
        Полный текст транскрипции.
    """
    settings = get_settings()
    cloud_config = settings.stt.cloud_ru
    max_upload_bytes = cloud_config.max_upload_bytes
    chunk_duration_seconds = cloud_config.chunk_duration_seconds
    chunk_bitrate_kbps = cloud_config.chunk_bitrate_kbps
    chunk_sample_rate_hz = cloud_config.chunk_sample_rate_hz
    chunk_channels = cloud_config.chunk_channels

    if stt_client is None:
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
            return validate_stt_result_text(
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
            if not is_stt_format_not_recognized_error(exc):
                raise
            logger.warning(
                "STT single request returned format error; switching to chunked mode: "
                "job_id=%s file=%s mime=%s error=%s",
                job_id,
                file_name,
                mime_type,
                str(exc),
            )

    chunks = split_audio_for_stt_chunks(
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
        chunk_text = validate_stt_result_text(
            transcript_result=transcript_result,
            job_id=job_id,
            context=f"chunk_{index}",
        ).strip()
        if chunk_text != "":
            chunk_texts.append(chunk_text)
    if len(chunk_texts) == 0:
        raise ValueError(f"STT вернул пустые транскрипции для всех чанков job_id={job_id}.")
    return "\n".join(chunk_texts)
