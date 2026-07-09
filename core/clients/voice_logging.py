"""Structured-логи для voice STT/TTS (аналог core/clients/llm/logging.py)."""

from __future__ import annotations

from core.logging import get_logger
from core.logging.attributes import (
    EVENT_VOICE_STT_RESPONSE,
    EVENT_VOICE_TTS_RESPONSE,
    LOG_STT_AUDIO_BYTES,
    LOG_STT_CHUNK_COUNT,
    LOG_STT_DURATION_MS,
    LOG_STT_MODE,
    LOG_STT_MODEL,
    LOG_STT_PROVIDER,
    LOG_STT_TEXT_LENGTH,
    LOG_TTS_AUDIO_BYTES,
    LOG_TTS_DURATION_MS,
    LOG_TTS_LANGUAGE,
    LOG_TTS_PROVIDER,
    LOG_TTS_TEXT_LENGTH,
    LOG_TTS_TTFA_MS,
    LOG_TTS_VOICE,
)

_logger = get_logger(__name__)


def log_voice_stt_response(
    *,
    provider: str,
    duration_ms: float,
    audio_bytes: int,
    text_length: int,
    mode: str,
    model: str | None = None,
    chunk_count: int | None = None,
) -> None:
    fields: dict[str, str | int | float] = {
        LOG_STT_PROVIDER: provider,
        LOG_STT_DURATION_MS: round(duration_ms, 2),
        LOG_STT_AUDIO_BYTES: audio_bytes,
        LOG_STT_TEXT_LENGTH: text_length,
        LOG_STT_MODE: mode,
    }
    if model is not None:
        fields[LOG_STT_MODEL] = model
    if chunk_count is not None:
        fields[LOG_STT_CHUNK_COUNT] = chunk_count
    _logger.info(EVENT_VOICE_STT_RESPONSE, **fields)


def log_voice_tts_response(
    *,
    provider: str,
    duration_ms: float,
    text_length: int,
    audio_bytes: int,
    voice: str | None = None,
    language: str | None = None,
    ttfa_ms: float | None = None,
) -> None:
    fields: dict[str, str | int | float] = {
        LOG_TTS_PROVIDER: provider,
        LOG_TTS_DURATION_MS: round(duration_ms, 2),
        LOG_TTS_TEXT_LENGTH: text_length,
        LOG_TTS_AUDIO_BYTES: audio_bytes,
    }
    if voice is not None:
        fields[LOG_TTS_VOICE] = voice
    if language is not None:
        fields[LOG_TTS_LANGUAGE] = language
    if ttfa_ms is not None:
        fields[LOG_TTS_TTFA_MS] = round(ttfa_ms, 2)
    _logger.info(EVENT_VOICE_TTS_RESPONSE, **fields)
