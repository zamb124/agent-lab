"""
Конвертация голосовых в формат, который воспроизводит iOS/WebKit (<audio>): AAC в .m4a.

Браузеры на Chromium отдают audio/webm (Opus); без перекодирования iPhone показывает ошибку формата.
"""

from __future__ import annotations

import asyncio


class AudioTranscodeError(RuntimeError):
    """Не удалось перекодировать аудио для совместимости с iOS (нет ffmpeg или сбой ffmpeg)."""


import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, Tuple

def audio_needs_ios_compatible_transcode(content_type: str) -> bool:
    if not isinstance(content_type, str) or content_type.strip() == "":
        return False
    base = content_type.split(";")[0].strip().lower()
    if base in (
        "audio/webm",
        "audio/ogg",
        "application/ogg",
        "video/webm",
        "audio/flac",
        "audio/x-flac",
    ):
        return True
    if base.startswith("audio/webm") or base.startswith("video/webm"):
        return True
    return False


def sniff_ios_incompatible_audio_magic(data: bytes) -> Optional[str]:
    """
    Определяет WebM (EBML) или Ogg по сигнатуре, если Content-Type неверен.

    Returns:
        Суффикс для ffmpeg: ".webm" или ".ogg", либо None.
    """
    if len(data) < 4:
        return None
    if data[:4] == b"\x1a\x45\xdf\xa3":
        return ".webm"
    if data[:4] == b"OggS":
        return ".ogg"
    return None


def resolve_ios_transcode_source(
    content_type: str,
    original_name: str,
    data: bytes,
) -> Tuple[bool, str]:
    """
    Нужно ли перекодировать загрузку в AAC/M4A и с каким суффиксом исходника вызывать ffmpeg.

    Учитывает MIME, расширение имени и магические байты (обход неверного Content-Type).
    """
    if audio_needs_ios_compatible_transcode(content_type or ""):
        magic = sniff_ios_incompatible_audio_magic(data)
        if magic:
            return True, magic
        suf = Path(original_name).suffix.lower()
        if suf in (".ogg", ".oga", ".opus"):
            return True, ".ogg"
        if suf == ".webm":
            return True, ".webm"
        if suf in (".flac",):
            return True, ".flac"
        if suf:
            return True, suf
        return True, ".webm"

    magic = sniff_ios_incompatible_audio_magic(data)
    if magic:
        return True, magic

    ext = Path(original_name).suffix.lower()
    if ext in (".webm",):
        return True, ".webm"
    if ext in (".ogg", ".oga", ".opus"):
        return True, ".ogg"
    if ext in (".flac",):
        return True, ".flac"

    return False, ".bin"


def _transcode_sync(data: bytes, ffmpeg: str, source_suffix: str) -> bytes:
    if len(data) == 0:
        raise ValueError("Пустые данные для перекодирования аудио.")
    suffix = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
    if suffix == ".":
        suffix = ".webm"
    with tempfile.TemporaryDirectory(prefix="platform-audio-transcode-") as td:
        work = Path(td)
        src = work / f"source{suffix}"
        dst = work / "out.m4a"
        src.write_bytes(data)
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-vn",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "1",
                "-movflags",
                "+faststart",
                str(dst),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise AudioTranscodeError(
                f"ffmpeg не смог перекодировать аудио для iOS: {stderr[:1200]}"
            )
        if not dst.is_file():
            raise AudioTranscodeError("ffmpeg не создал выходной файл .m4a.")
        out = dst.read_bytes()
        if len(out) == 0:
            raise AudioTranscodeError("Перекодированное аудио пустое.")
        return out


async def transcode_audio_bytes_to_m4a_aac(data: bytes, source_suffix: str) -> bytes:
    """
    Перекодирует вход в AAC внутри контейнера M4A (совместимо с iOS Safari и WKWebView).

    Raises:
        RuntimeError: нет ffmpeg или сбой ffmpeg.
        ValueError: пустой вход.
    """
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise AudioTranscodeError(
            "ffmpeg не найден в PATH: нельзя перекодировать голосовое для iOS."
        )
    return await asyncio.to_thread(_transcode_sync, data, ffmpeg, source_suffix)
