"""Длительность аудио из байтов через ffprobe (без pydub — совместимость с Python 3.13+)."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import tempfile
from pathlib import Path


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
            src.write_bytes(data)
            result = subprocess.run(
                [
                    ffprobe,
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(src),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                stderr = (result.stderr or "").strip()
                raise ValueError(f"ffprobe завершился с ошибкой: {stderr[:800]}")
            out = (result.stdout or "").strip()
            if out == "":
                raise ValueError("ffprobe не вернул длительность.")
            return float(out)

    seconds = await asyncio.to_thread(_run)
    if not (seconds > 0) or seconds != seconds:
        raise ValueError(f"Некорректная длительность от ffprobe: {seconds!r}")
    return int(round(seconds * 1000))
