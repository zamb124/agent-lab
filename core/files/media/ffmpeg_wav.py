"""Нормализация произвольного аудиоконтейнера в WAV PCM s16le mono 16 kHz через ffmpeg."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

STT_WAV_SAMPLE_RATE = 16000

_CONTENT_TYPE_SUFFIX = {
    "webm": ".webm",
    "ogg": ".ogg",
    "mpeg": ".mp3",
    "mp3": ".mp3",
    "wav": ".wav",
    "x-wav": ".wav",
    "flac": ".flac",
    "x-flac": ".flac",
    "mp4": ".mp4",
    "x-m4a": ".m4a",
    "aac": ".aac",
}


def _input_suffix(*, audio_bytes: bytes, file_name: str, content_type: str) -> str:
    if not audio_bytes:
        raise ValueError("_input_suffix: audio_bytes пустой.")
    if audio_bytes[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if audio_bytes[:4] == b"RIFF":
        return ".wav"
    if audio_bytes[:4] == b"OggS":
        return ".ogg"
    if audio_bytes[:4] == b"fLaC":
        return ".flac"
    suffix = Path(file_name).suffix.lower()
    if suffix != "":
        return suffix
    if content_type == "":
        raise ValueError(
            "Неизвестный аудиоконтейнер: нет расширения файла и пустой content_type."
        )
    base = content_type.split(";", 1)[0].strip().lower()
    if "/" not in base:
        raise ValueError(f"Неизвестный audio content_type={content_type!r} без расширения файла.")
    subtype = base.split("/", 1)[1]
    mapped = _CONTENT_TYPE_SUFFIX.get(subtype)
    if mapped is None:
        raise ValueError(
            f"Неизвестный audio content_type={content_type!r} без расширения файла."
        )
    return mapped


def transcode_audio_bytes_to_wav_pcm16_mono(
    *,
    audio_bytes: bytes,
    file_name: str,
    content_type: str,
    sample_rate: int = STT_WAV_SAMPLE_RATE,
) -> bytes:
    if not audio_bytes:
        raise ValueError("transcode_audio_bytes_to_wav_pcm16_mono: audio_bytes пустой.")
    if sample_rate <= 0:
        raise ValueError("transcode_audio_bytes_to_wav_pcm16_mono: sample_rate должен быть > 0.")
    if file_name == "":
        raise ValueError("transcode_audio_bytes_to_wav_pcm16_mono: file_name не может быть пустым.")
    suffix = _input_suffix(
        audio_bytes=audio_bytes,
        file_name=file_name,
        content_type=content_type,
    )
    with tempfile.TemporaryDirectory(prefix="stt-wav-") as work_dir:
        source_path = Path(work_dir) / f"source{suffix}"
        out_path = Path(work_dir) / "normalized.wav"
        _ = source_path.write_bytes(audio_bytes)
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
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
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
            raise ValueError(
                "Не удалось нормализовать аудио в WAV для STT. "
                + f"return_code={ffmpeg_result.returncode}; stderr={stderr}"
            )
        wav_bytes = out_path.read_bytes()
        if len(wav_bytes) == 0:
            raise ValueError("Нормализация STT дала пустой WAV.")
        if wav_bytes[:4] != b"RIFF":
            raise ValueError("Нормализация STT не дала WAV (нет RIFF).")
        return wav_bytes


__all__ = [
    "STT_WAV_SAMPLE_RATE",
    "transcode_audio_bytes_to_wav_pcm16_mono",
]
