"""Парсинг вывода ffmpeg volumedetect."""

from __future__ import annotations

import pytest

from core.files.audio_silence import parse_volumedetect_max_volume_db


def test_parse_volumedetect_max_volume_db_extracts_value() -> None:
    stderr = (
        "…\n"
        "[Parsed_volumedetect_0 @ 0x…] mean_volume: -27.0 dB\n"
        "[Parsed_volumedetect_0 @ 0x…] max_volume: -4.5 dB\n"
    )
    assert parse_volumedetect_max_volume_db(stderr) == -4.5


def test_parse_volumedetect_max_volume_db_missing_raises() -> None:
    with pytest.raises(ValueError, match="max_volume"):
        parse_volumedetect_max_volume_db("no stats here")
