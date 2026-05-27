"""Длительность аудио из байтов через ffprobe (без pydub — совместимость с Python 3.13+)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path

from core.models import FlexibleBaseModel


class FfprobeDurationNode(FlexibleBaseModel):
    """Duration fragment emitted by ffprobe format/stream sections."""

    duration: str | None = None


class FfprobeDurationPayload(FlexibleBaseModel):
    """Typed ffprobe payload for duration probing."""

    format: FfprobeDurationNode | None = None
    streams: list[FfprobeDurationNode]


async def probe_audio_duration_seconds_from_upload(*, data: bytes, file_name: str) -> float:
    """Длительность контейнерного аудио в секундах (ffprobe); Zero-Guess при ошибке — исключение."""
    raw_name = file_name.strip()
    if raw_name == "":
        raise ValueError("file_name для ffprobe не может быть пустым.")
    suffix = Path(raw_name).suffix
    effective_suffix = suffix if suffix != "" else ".bin"
    ms = await probe_audio_duration_ms_from_bytes(data, effective_suffix)
    return ms / 1000.0


def _duration_text_to_seconds(duration: str | None) -> float | None:
    if duration is None:
        return None
    duration_text = duration.strip()
    if duration_text == "" or duration_text.upper() == "N/A":
        return None
    return float(duration_text)


def _parse_duration_from_json(raw: str) -> float:
    """Извлекает duration из JSON-вывода ffprobe (format и stream уровни).

    Для контейнерных форматов (mp4, m4a) длительность лежит в format.duration.
    Для стриминговых (ogg-сегменты из LiveKit egress) format.duration = N/A,
    но stream-уровень содержит корректное значение.
    """
    payload = FfprobeDurationPayload.model_validate_json(raw)
    if payload.format is not None:
        format_seconds = _duration_text_to_seconds(payload.format.duration)
        if format_seconds is not None:
            return format_seconds
    for stream in payload.streams:
        stream_seconds = _duration_text_to_seconds(stream.duration)
        if stream_seconds is not None:
            return stream_seconds
    raise ValueError(
        "ffprobe не вернул длительность ни на уровне format, ни stream. "
        + f"probe={payload.model_dump(mode='json')!r}"
    )


async def probe_audio_duration_ms_from_bytes(data: bytes, source_suffix: str) -> int:
    if len(data) == 0:
        raise ValueError("Пустые данные для ffprobe.")
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        raise ValueError("ffprobe не найден в PATH.")
    suf = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
    if suf == ".":
        suf = ".bin"

    def _run() -> float:
        with tempfile.TemporaryDirectory(prefix="platform-audio-probe-") as td:
            src = Path(td) / f"in{suf}"
            _ = src.write_bytes(data)
            result = subprocess.run(
                [
                    ffprobe,
                    "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "format=duration:stream=duration",
                    "-of", "json",
                    str(src),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                raise ValueError(f"ffprobe завершился с ошибкой: {stderr[:800]}")
            raw = (result.stdout or "").strip()
            if raw == "":
                raise ValueError("ffprobe вернул пустой вывод.")
            return _parse_duration_from_json(raw)

    seconds = await asyncio.to_thread(_run)
    if not (seconds > 0) or seconds != seconds:
        raise ValueError(f"Некорректная длительность от ffprobe: {seconds!r}")
    return int(round(seconds * 1000))
