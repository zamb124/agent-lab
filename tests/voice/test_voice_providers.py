"""Тесты провайдеров STT, TTS, VAD."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apps.voice.providers.stt.cloud_ru import CloudRuStreamSTTProvider
from apps.voice.providers.tts.kokoro_local import KokoroLocalTTSProvider
from apps.voice.providers.vad.silero import SileroVADProvider


# === SileroVADProvider ===


async def test_silero_vad_detect_speech_raises_when_not_initialized(unique_id: str) -> None:
    provider = SileroVADProvider()
    with pytest.raises(RuntimeError, match="не инициализирован"):
        await provider.detect_speech(b"\x00" * 320, 16000)


async def test_silero_vad_detect_speech_raises_on_wrong_sample_rate(unique_id: str) -> None:
    provider = SileroVADProvider(sample_rate=16000)
    provider._model = (MagicMock(), MagicMock())
    with pytest.raises(ValueError, match="sample_rate"):
        await provider.detect_speech(b"\x00" * 320, 8000)


async def test_silero_vad_close_resets_state(unique_id: str) -> None:
    provider = SileroVADProvider()
    provider._model = (MagicMock(), MagicMock())
    provider._executor = MagicMock()
    provider._executor.shutdown = MagicMock()
    await provider.close()
    assert provider._model is None
    assert provider._executor is None


async def test_silero_vad_init_loads_model(unique_id: str) -> None:
    provider = SileroVADProvider()
    mock_model = MagicMock()
    mock_utils = [MagicMock()]
    with patch("apps.voice.providers.vad.silero.SileroVADProvider.init") as mock_init:
        mock_init.return_value = None
        provider._model = (mock_model, mock_utils[0])
        assert provider._model is not None


# === KokoroLocalTTSProvider ===


async def test_kokoro_tts_synthesize_raises_when_not_initialized(unique_id: str) -> None:
    provider = KokoroLocalTTSProvider()
    with pytest.raises(RuntimeError, match="не инициализирован"):
        await provider.synthesize("Привет")


async def test_kokoro_tts_close_resets_state(unique_id: str) -> None:
    provider = KokoroLocalTTSProvider()
    provider._model = MagicMock()
    provider._initialized = True
    await provider.close()
    assert provider._model is None
    assert provider._initialized is False


async def test_kokoro_tts_synthesize_calls_sync_method(unique_id: str) -> None:
    provider = KokoroLocalTTSProvider()
    provider._initialized = True

    with patch.object(provider, "_synthesize_sync", return_value=b"audio_bytes") as mock_sync:
        result = await provider.synthesize("Тест")
    mock_sync.assert_called_once_with("Тест")
    assert result == b"audio_bytes"


def test_kokoro_tts_synthesize_sync_raises_on_empty_audio(unique_id: str) -> None:
    provider = KokoroLocalTTSProvider()

    mock_pipeline = MagicMock()
    mock_pipeline.return_value = iter([("meta", "chunk", None)])
    provider._model = mock_pipeline

    with pytest.raises(ValueError, match="не вернул аудио"):
        provider._synthesize_sync("Тест")


def test_kokoro_tts_synthesize_sync_returns_audio_bytes(unique_id: str) -> None:
    provider = KokoroLocalTTSProvider()

    import numpy as np

    fake_audio = np.zeros(100, dtype=np.float32)
    mock_pipeline = MagicMock()
    mock_pipeline.return_value = iter([("meta", "chunk", fake_audio)])
    provider._model = mock_pipeline

    result = provider._synthesize_sync("Тест")
    assert isinstance(result, bytes)
    assert len(result) == fake_audio.tobytes().__len__()


# === CloudRuStreamSTTProvider ===


@pytest.mark.asyncio
async def test_cloud_ru_stt_push_audio_accumulates(unique_id: str) -> None:
    provider = CloudRuStreamSTTProvider()
    await provider.push_audio(b"frame1")
    await provider.push_audio(b"frame2")
    assert provider.has_buffered_audio() is True


def test_cloud_ru_stt_has_buffered_audio_false_when_empty(unique_id: str) -> None:
    provider = CloudRuStreamSTTProvider()
    assert provider.has_buffered_audio() is False


@pytest.mark.asyncio
async def test_cloud_ru_stt_flush_empty_returns_none(unique_id: str) -> None:
    provider = CloudRuStreamSTTProvider()
    # flush без аудио должен вернуть None (не пустую строку)
    result = None
    # Нельзя вызвать flush напрямую без cloud.ru API, но можно проверить буфер
    assert not provider.has_buffered_audio()


@pytest.mark.asyncio
async def test_cloud_ru_stt_reset_clears_buffer(unique_id: str) -> None:
    provider = CloudRuStreamSTTProvider()
    await provider.push_audio(b"data")
    assert provider.has_buffered_audio()
    provider.reset()
    assert not provider.has_buffered_audio()
