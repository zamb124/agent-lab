"""ffmpeg: любой контейнер → WAV PCM s16le mono 16 kHz для batch STT."""

from __future__ import annotations

import pytest

from core.files.media.ffmpeg_wav import transcode_audio_bytes_to_wav_pcm16_mono
from tests.fixtures.audio_bytes import minimal_wav_silence


def test_transcode_wav_stays_riff() -> None:
    wav_bytes = minimal_wav_silence(duration_sec=0.2)
    out = transcode_audio_bytes_to_wav_pcm16_mono(
        audio_bytes=wav_bytes,
        file_name="voice.wav",
        content_type="audio/wav",
    )
    assert out[:4] == b"RIFF"
    assert out[8:12] == b"WAVE"


def test_transcode_webm_garbage_raises() -> None:
    garbage = b"\x1a\x45\xdf\xa3" + b"not-a-webm-payload"
    with pytest.raises(ValueError, match="Не удалось нормализовать аудио"):
        transcode_audio_bytes_to_wav_pcm16_mono(
            audio_bytes=garbage,
            file_name="speech.webm",
            content_type="audio/webm",
        )


def test_transcode_empty_raises() -> None:
    with pytest.raises(ValueError, match="пустой"):
        transcode_audio_bytes_to_wav_pcm16_mono(
            audio_bytes=b"",
            file_name="voice.wav",
            content_type="audio/wav",
        )
