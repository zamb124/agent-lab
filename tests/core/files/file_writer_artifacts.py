"""Артефакты тестов FileWriter: перезапись в каталоге рядом с тестами."""

from __future__ import annotations

from pathlib import Path

OUTPUT_DIR = Path(__file__).resolve().parent / "file_writer_output"


def overwrite_artifact(filename: str, data: bytes) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_bytes(data)
    return path
