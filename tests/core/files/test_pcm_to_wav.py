from __future__ import annotations

import pytest

from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav


def test_pcm_s16le_mono_to_wav_riff_header(unique_id: str) -> None:
    wav = pcm_s16le_mono_to_wav(b"\x00\x00" * 10, sample_rate=16000)
    assert wav.startswith(b"RIFF")
    assert wav[8:12] == b"WAVE"


def test_pcm_s16le_mono_to_wav_rejects_odd_length(unique_id: str) -> None:
    with pytest.raises(ValueError, match="чётная"):
        pcm_s16le_mono_to_wav(b"\x00\x00\x00", sample_rate=16000)
