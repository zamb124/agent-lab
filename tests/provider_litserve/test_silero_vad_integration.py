"""LocalVADEngine: реальный Silero VAD на синтетическом аудио (без моков).

Маркеры ``integration`` + ``slow``: модель Silero VAD весит ~2 MB и
загружается один раз в session-фикстуре ``shared_silero_vad_engine``
(см. ``conftest.py``). Каждый тест работает с уже загруженной моделью —
обычный per-test timeout 15 секунд достаточно.

Запуск:

    uv run --python 3.13 pytest tests/provider_litserve/test_silero_vad_integration.py \\
        --confcutdir=tests/provider_litserve \\
        -m "integration and slow" -v
"""

from __future__ import annotations

import math
import struct

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.timeout(15),
]


def _generate_pcm16_silence(*, sample_rate: int, duration_s: float) -> bytes:
    n = int(sample_rate * duration_s)
    return struct.pack(f"<{n}h", *([0] * n))


def _generate_pcm16_tone(
    *, sample_rate: int, duration_s: float, frequency_hz: float, amplitude: float = 0.5
) -> bytes:
    """Чистая синусоида в PCM-16 mono."""
    n = int(sample_rate * duration_s)
    samples: list[int] = []
    two_pi_f = 2.0 * math.pi * frequency_hz
    for i in range(n):
        v = amplitude * math.sin(two_pi_f * i / sample_rate)
        samples.append(int(max(-1.0, min(1.0, v)) * 32767))
    return struct.pack(f"<{n}h", *samples)


def test_silero_vad_detects_no_segments_on_pure_silence(shared_silero_vad_engine):
    engine, _cfg, api_id = shared_silero_vad_engine
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=2.0)
    segments = engine.detect_segments(
        audio_bytes=pcm,
        api_model_id=api_id,
        sample_rate_override=None,
    )
    assert segments == []


def test_silero_vad_returns_list_for_synthetic_tone(shared_silero_vad_engine):
    engine, _cfg, api_id = shared_silero_vad_engine
    pcm = (
        _generate_pcm16_silence(sample_rate=16000, duration_s=0.4)
        + _generate_pcm16_tone(
            sample_rate=16000, duration_s=1.5, frequency_hz=220.0, amplitude=0.7
        )
        + _generate_pcm16_silence(sample_rate=16000, duration_s=0.4)
    )
    segments = engine.detect_segments(
        audio_bytes=pcm,
        api_model_id=api_id,
        sample_rate_override=None,
    )
    assert isinstance(segments, list)
    for seg in segments:
        assert "start" in seg and "end" in seg
        assert seg["end"] > seg["start"]
        assert 0.0 <= seg["start"] <= 2.4
        assert 0.0 <= seg["end"] <= 2.4


def test_silero_vad_unknown_model_raises_value_error(
    shared_silero_vad_engine, unique_id
):
    engine, _cfg, _api_id = shared_silero_vad_engine
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=0.2)
    with pytest.raises(ValueError, match="неизвестная модель"):
        engine.detect_segments(
            audio_bytes=pcm,
            api_model_id=f"unknown-{unique_id}",
            sample_rate_override=None,
        )
