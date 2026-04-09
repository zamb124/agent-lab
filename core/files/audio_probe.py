"""Длительность аудио из байтов через ffprobe (без pydub — совместимость с Python 3.13+)."""

from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path


def _parse_duration_from_json(raw: str) -> float:
    """Извлекает duration из JSON-вывода ffprobe (format и stream уровни).

    Для контейнерных форматов (mp4, m4a) длительность лежит в format.duration.
    Для стриминговых (ogg-сегменты из LiveKit egress) format.duration = N/A,
    но stream-уровень содержит корректное значение.
    """
    probe = json.loads(raw)
    for source in ("format", "streams"):
        node = probe.get(source)
        if node is None:
            continue
        if isinstance(node, list):
            for entry in node:
                val = entry.get("duration")
                if isinstance(val, str) and val.upper() != "N/A" and val.strip() != "":
                    return float(val)
        elif isinstance(node, dict):
            val = node.get("duration")
            if isinstance(val, str) and val.upper() != "N/A" and val.strip() != "":
                return float(val)
    raise ValueError(f"ffprobe не вернул длительность ни на уровне format, ни stream. probe={probe!r}")


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
