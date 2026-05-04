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
from core.clients.stt_client import BaseSTTClient, MockSTTClient, STTTranscriptionResult
from core.files.models import AudioTranscriptionStatus
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
async def test_streaming_stt_flush_posts_wav_to_batch_client(unique_id: str) -> None:
    class CaptureSTT(BaseSTTClient):
        def __init__(self) -> None:
            self.calls: dict[str, object] = {}

        async def transcribe_audio(
            self,
            *,
            audio_bytes: bytes,
            file_name: str,
            mime_type: str,
            language: str | None = None,
        ) -> STTTranscriptionResult:
            self.calls = {
                "file_name": file_name,
                "mime_type": mime_type,
                "is_wav": audio_bytes.startswith(b"RIFF"),
            }
            return STTTranscriptionResult(
                provider="capture",
                status=AudioTranscriptionStatus.DONE,
                text="ok",
                language=language,
            )

    cap = CaptureSTT()
    provider = StreamingSTTProvider(stt_client=cap)
    await provider.push_audio(b"\x00\x00" * 160)
    await provider.flush_buffer()
    assert cap.calls["file_name"] == "voice_segment.wav"
    assert cap.calls["mime_type"] == "audio/wav"
    assert cap.calls["is_wav"] is True


@pytest.mark.asyncio
async def test_streaming_stt_reset_clears_buffer(unique_id: str) -> None:
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text="ок"))
    await provider.push_audio(b"data")
    assert provider.has_buffered_audio()
    provider.reset()
    assert not provider.has_buffered_audio()


@pytest.mark.asyncio
async def test_streaming_stt_peek_returns_text_without_clearing_buffer(
    unique_id: str,
) -> None:
    """peek_transcript отдаёт результат и оставляет буфер для дальнейшего накопления."""
    provider = StreamingSTTProvider(
        stt_client=MockSTTClient(transcript_text=f"partial-{unique_id}")
    )
    await provider.push_audio(b"\x00\x00" * 16000)
    result = await provider.peek_transcript(min_buffer_bytes=8000)
    assert result is not None
    assert result.text == f"partial-{unique_id}"
    assert provider.has_buffered_audio()


@pytest.mark.asyncio
async def test_streaming_stt_peek_below_threshold_returns_none(unique_id: str) -> None:
    """При буфере короче min_buffer_bytes — None, batch-провайдер не дёргается."""
    provider = StreamingSTTProvider(
        stt_client=MockSTTClient(transcript_text="x")
    )
    await provider.push_audio(b"\x00\x00" * 100)
    result = await provider.peek_transcript(min_buffer_bytes=16000)
    assert result is None
    assert provider.has_buffered_audio()


@pytest.mark.asyncio
async def test_streaming_stt_peek_then_flush_returns_full_segment(
    unique_id: str,
) -> None:
    """После peek можно дописать ещё PCM и flush_buffer вернёт всё."""
    provider = StreamingSTTProvider(stt_client=MockSTTClient(transcript_text="full"))
    await provider.push_audio(b"\x00\x00" * 8000)
    peeked = await provider.peek_transcript(min_buffer_bytes=2000)
    assert peeked is not None
    await provider.push_audio(b"\x00\x00" * 8000)
    flushed = await provider.flush_buffer()
    assert flushed is not None
    assert flushed.text == "full"
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
