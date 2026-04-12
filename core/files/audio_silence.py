"""Анализ громкости и обрезка кромочной тишины через ffmpeg (speech-to-chat, сегменты egress)."""

from __future__ import annotations

import asyncio
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_volumedetect_max_volume_db(stderr_text: str) -> float:
    m = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr_text)
    if m is None:
        raise ValueError("В stderr ffmpeg (volumedetect) не найдено поле max_volume.")
    return float(m.group(1))


def _suffix_for_ffmpeg(source_suffix: str) -> str:
    suf = source_suffix if source_suffix.startswith(".") else f".{source_suffix}"
    if suf == ".":
        return ".bin"
    return suf


def _volumedetect_sync(data: bytes, source_suffix: str, ffmpeg: str) -> float:
    if len(data) == 0:
        raise ValueError("Пустые данные для volumedetect.")
    suf = _suffix_for_ffmpeg(source_suffix)
    with tempfile.TemporaryDirectory(prefix="platform-volumedetect-") as td:
        src = Path(td) / f"in{suf}"
        src.write_bytes(data)
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostats",
                "-i",
                str(src),
                "-af",
                "volumedetect",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise ValueError(f"volumedetect: ffmpeg завершился с ошибкой: {stderr[:800]}")
        return parse_volumedetect_max_volume_db(result.stderr or "")


async def volumedetect_max_volume_db_from_bytes(data: bytes, source_suffix: str) -> float:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg не найден в PATH.")
    return await asyncio.to_thread(_volumedetect_sync, data, source_suffix, ffmpeg)


def _silenceremove_chain(*, threshold_db: float, min_silence_sec: float) -> str:
    t = f"{threshold_db:.2f}dB"
    ms = f"{min_silence_sec:.3f}"
    return (
        f"silenceremove=start_periods=1:start_duration={ms}:start_threshold={t}:detection=peak,"
        f"areverse,silenceremove=start_periods=1:start_duration={ms}:start_threshold={t}:detection=peak,"
        "areverse"
    )


def _trim_edges_sync(
    data: bytes,
    ffmpeg: str,
    source_suffix: str,
    *,
    threshold_db: float,
    min_silence_sec: float,
) -> bytes:
    if len(data) == 0:
        raise ValueError("Пустые данные для обрезки тишины.")
    suf = _suffix_for_ffmpeg(source_suffix)
    ext = suf.lower()
    with tempfile.TemporaryDirectory(prefix="platform-trim-silence-") as td:
        work = Path(td)
        src = work / f"in{suf}"
        src.write_bytes(data)
        if ext == ".wav":
            dst = work / "out.wav"
            enc_args = ["-c:a", "pcm_s16le"]
        else:
            dst = work / "out.m4a"
            enc_args = [
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "1",
                "-movflags",
                "+faststart",
            ]
        chain = _silenceremove_chain(
            threshold_db=threshold_db, min_silence_sec=min_silence_sec
        )
        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(src),
                "-af",
                chain,
                *enc_args,
                str(dst),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise ValueError(f"silenceremove: ffmpeg завершился с ошибкой: {stderr[:1200]}")
        if not dst.is_file():
            raise ValueError("silenceremove: выходной файл не создан.")
        out = dst.read_bytes()
        if len(out) == 0:
            raise ValueError("silenceremove: выход пустой.")
        return out


async def trim_leading_trailing_silence_from_bytes(
    data: bytes,
    *,
    source_suffix: str,
    threshold_db: float,
    min_silence_sec: float,
) -> bytes:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise ValueError("ffmpeg не найден в PATH.")
    return await asyncio.to_thread(
        _trim_edges_sync,
        data,
        ffmpeg,
        source_suffix,
        threshold_db=threshold_db,
        min_silence_sec=min_silence_sec,
    )
