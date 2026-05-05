from __future__ import annotations

import io
import wave

import pytest

from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav
from core.files.media.wav_merge import merge_wav_s16le_mono_files


def test_merge_wav_s16le_mono_files_concatenates_frames(unique_id: str) -> None:
    w1 = pcm_s16le_mono_to_wav(b"\x01\x00" * 40, sample_rate=16000)
    w2 = pcm_s16le_mono_to_wav(b"\x02\x00" * 60, sample_rate=16000)
    merged = merge_wav_s16le_mono_files([w1, w2])
    with wave.open(io.BytesIO(merged), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        assert w.getframerate() == 16000
        assert w.getnframes() == 100


def test_merge_wav_s16le_mono_files_rejects_empty(unique_id: str) -> None:
    with pytest.raises(ValueError, match="пуст"):
        merge_wav_s16le_mono_files([])
