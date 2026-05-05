"""BatchBackedTTSStreamer: отсутствие тихого пустого PCM."""

from __future__ import annotations

import pytest

from core.clients.tts_client import BaseTTSClient, TTSResult
from core.clients.tts_streaming import BatchBackedTTSStreamer


class _EmptyAudioTTSClient(BaseTTSClient):
    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        chosen_format = response_format or "wav"
        return TTSResult(
            provider="empty_fixture",
            audio_bytes=b"",
            mime_type="audio/wav",
            sample_rate=8000,
            response_format=chosen_format,
            voice=voice,
            model="fixture",
        )


@pytest.mark.asyncio
async def test_batch_backed_raises_when_upstream_audio_empty() -> None:
    streamer = BatchBackedTTSStreamer(
        tts_client=_EmptyAudioTTSClient(),
        response_format="wav",
        sample_rate=8000,
        provider_name="empty_fixture",
        mime_type="audio/wav",
    )
    with pytest.raises(ValueError, match="пустой audio_bytes"):
        await streamer.synthesize_chunk("непустой текст")


class _NeverSynthesizeTTSClient(BaseTTSClient):
    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        raise AssertionError("synthesize must not run for whitespace-only chunk")


@pytest.mark.asyncio
async def test_batch_backed_whitespace_only_chunk_skips_http() -> None:
    streamer = BatchBackedTTSStreamer(
        tts_client=_NeverSynthesizeTTSClient(),
        response_format="wav",
        sample_rate=8000,
        provider_name="skip_ws",
        mime_type="audio/wav",
    )
    out = await streamer.synthesize_chunk("  \n\t ")
    assert out == b""
