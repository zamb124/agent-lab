"""GigaAM short-form ≤25 с; длиннее — окна 24 с, без transcribe_longform."""

from __future__ import annotations

import io
import wave

import pytest

from apps.provider_litserve.stt.engines import (
    GIGAAM_WINDOW_SECONDS,
    _GigaAMAdapter,
)
from core.config.models import ProviderLitserveInfraConfig

PCM16_SAMPLE_RATE = 16000


class _RecordingGigaAM:
    def __init__(self) -> None:
        self.paths: list[str] = []

    def to(self, device: str) -> _RecordingGigaAM:
        _ = device
        return self

    def transcribe(self, wav_path: str) -> str:
        if hasattr(self, "transcribe_longform"):
            raise AssertionError("Protocol не должен иметь transcribe_longform")
        self.paths.append(wav_path)
        return f"chunk-{len(self.paths)}"


def _pcm16_silence(*, seconds: float) -> bytes:
    sample_count = int(seconds * PCM16_SAMPLE_RATE)
    if sample_count <= 0:
        raise ValueError("seconds должен быть > 0")
    return b"\x00\x00" * sample_count


def _wav_silence(*, seconds: float) -> bytes:
    pcm = _pcm16_silence(seconds=seconds)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(PCM16_SAMPLE_RATE)
        wf.writeframes(pcm)
    return buf.getvalue()


def test_gigaam_adapter_short_audio_one_transcribe() -> None:
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    model = _RecordingGigaAM()
    text = adapter.transcribe(model, _wav_silence(seconds=1.0), None)
    assert text == "chunk-1"
    assert len(model.paths) == 1


def test_gigaam_adapter_exactly_25s_one_transcribe() -> None:
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    model = _RecordingGigaAM()
    text = adapter.transcribe(model, _wav_silence(seconds=25.0), None)
    assert text == "chunk-1"
    assert len(model.paths) == 1


def test_gigaam_adapter_empty_wav_raises() -> None:
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    model = _RecordingGigaAM()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(PCM16_SAMPLE_RATE)
        wf.writeframes(b"")
    with pytest.raises(ValueError, match="empty audio data"):
        adapter.transcribe(model, buf.getvalue(), None)


def test_gigaam_adapter_over_25s_windows_without_longform() -> None:
    adapter = _GigaAMAdapter(ProviderLitserveInfraConfig(), "cpu")
    model = _RecordingGigaAM()
    text = adapter.transcribe(model, _wav_silence(seconds=26.0), None)
    expected_calls = 2
    assert 26.0 > GIGAAM_WINDOW_SECONDS
    assert len(model.paths) == expected_calls
    assert text == "chunk-1 chunk-2"
    assert not hasattr(model, "transcribe_longform")
