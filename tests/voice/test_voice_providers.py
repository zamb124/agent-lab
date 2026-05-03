"""Тесты универсальных streaming-адаптеров для STT/TTS/VAD.

Используем mock batch-клиенты из core.clients.{stt,tts,vad}_client
(не unittest.mock) для проверки контракта адаптеров.
"""

from __future__ import annotations

import pytest

from apps.voice.providers.streaming_adapters import (
    StreamingSTTProvider,
    StreamingTTSProvider,
    StreamingVADProvider,
)
from core.clients.stt_client import MockSTTClient
from core.clients.tts_client import MockTTSClient
from core.clients.vad_client import MockVADClient


# === StreamingSTTProvider ===


@pytest.mark.asyncio
async def test_streaming_stt_push_audio_accumulates(unique_id: str) -> None:
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text="ок"))
    await provider.push_audio(b"frame1")
    await provider.push_audio(b"frame2")
    assert provider.has_buffered_audio() is True


@pytest.mark.asyncio
async def test_streaming_stt_flush_empty_returns_none(unique_id: str) -> None:
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text="ок"))
    result = await provider.flush_buffer()
    assert result is None


@pytest.mark.asyncio
async def test_streaming_stt_flush_returns_transcription(unique_id: str) -> None:
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text=f"text-{unique_id}"))
    await provider.push_audio(b"\x00" * 320)
    result = await provider.flush_buffer()
    assert result is not None
    assert result.text == f"text-{unique_id}"
    assert provider.has_buffered_audio() is False


@pytest.mark.asyncio
async def test_streaming_stt_reset_clears_buffer(unique_id: str) -> None:
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text="ок"))
    await provider.push_audio(b"data")
    assert provider.has_buffered_audio()
    provider.reset()
    assert not provider.has_buffered_audio()


# === StreamingTTSProvider ===


@pytest.mark.asyncio
async def test_streaming_tts_synthesize_raises_when_not_initialized(unique_id: str) -> None:
    provider = StreamingTTSProvider(tts_client=MockTTSClient())
    with pytest.raises(RuntimeError, match="не инициализирован"):
        await provider.synthesize("Привет")


@pytest.mark.asyncio
async def test_streaming_tts_synthesize_returns_bytes(unique_id: str) -> None:
    provider = StreamingTTSProvider(tts_client=MockTTSClient())
    await provider.init()
    audio = await provider.synthesize(f"text-{unique_id}")
    assert isinstance(audio, bytes)
    assert len(audio) > 0


@pytest.mark.asyncio
async def test_streaming_tts_synthesize_rejects_empty_text(unique_id: str) -> None:
    provider = StreamingTTSProvider(tts_client=MockTTSClient())
    await provider.init()
    with pytest.raises(ValueError, match="пустой text"):
        await provider.synthesize("")


# === StreamingVADProvider ===


@pytest.mark.asyncio
async def test_streaming_vad_returns_false_for_short_buffer(unique_id: str) -> None:
    provider = StreamingVADProvider(
        vad_client=MockVADClient(),
        sample_rate=16000,
        window_ms=200,
    )
    is_speech = await provider.detect_speech(b"\x00\x00" * 32, 16000)
    assert is_speech is False


@pytest.mark.asyncio
async def test_streaming_vad_detects_speech_after_window(unique_id: str) -> None:
    provider = StreamingVADProvider(
        vad_client=MockVADClient(),
        sample_rate=16000,
        window_ms=100,
    )
    pcm_window = b"\x01\x00" * 1600
    is_speech = await provider.detect_speech(pcm_window, 16000)
    assert is_speech is True


@pytest.mark.asyncio
async def test_streaming_vad_raises_on_wrong_sample_rate(unique_id: str) -> None:
    provider = StreamingVADProvider(
        vad_client=MockVADClient(),
        sample_rate=16000,
    )
    with pytest.raises(ValueError, match="sample_rate"):
        await provider.detect_speech(b"\x00\x00" * 320, 8000)
