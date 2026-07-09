"""Обёртки STT/TTS-клиентов с structured latency-логами для Grafana."""

from __future__ import annotations

import time
from typing import override

from core.clients.stt_client import BaseSTTClient, STTTranscriptionResult
from core.clients.tts_client import BaseTTSClient, TTSResult
from core.clients.voice_logging import log_voice_stt_response, log_voice_tts_response


class ObservedSTTClient(BaseSTTClient):
    """Декоратор BaseSTTClient: пишет voice_stt_response после каждого вызова."""

    _delegate: BaseSTTClient
    _provider: str
    _model: str | None
    _mode: str

    def __init__(
        self,
        delegate: BaseSTTClient,
        *,
        provider: str,
        model: str | None = None,
        mode: str = "batch",
    ) -> None:
        self._delegate = delegate
        self._provider = provider
        self._model = model
        self._mode = mode

    @override
    async def transcribe_audio(
        self,
        *,
        audio_bytes: bytes,
        file_name: str,
        content_type: str,
        language: str | None = None,
    ) -> STTTranscriptionResult:
        start = time.perf_counter()
        result = await self._delegate.transcribe_audio(
            audio_bytes=audio_bytes,
            file_name=file_name,
            content_type=content_type,
            language=language,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_voice_stt_response(
            provider=result.provider or self._provider,
            model=self._model,
            duration_ms=duration_ms,
            audio_bytes=len(audio_bytes),
            text_length=len(result.text),
            mode=self._mode,
        )
        return result


class ObservedTTSClient(BaseTTSClient):
    """Декоратор BaseTTSClient: пишет voice_tts_response после каждого вызова."""

    _delegate: BaseTTSClient
    _provider: str
    _voice: str | None
    _language: str | None

    def __init__(
        self,
        delegate: BaseTTSClient,
        *,
        provider: str,
        voice: str | None = None,
        language: str | None = None,
    ) -> None:
        self._delegate = delegate
        self._provider = provider
        self._voice = voice
        self._language = language

    @override
    async def synthesize(
        self,
        *,
        text: str,
        voice: str | None = None,
        response_format: str | None = None,
        sample_rate: int | None = None,
    ) -> TTSResult:
        start = time.perf_counter()
        result = await self._delegate.synthesize(
            text=text,
            voice=voice,
            response_format=response_format,
            sample_rate=sample_rate,
        )
        duration_ms = (time.perf_counter() - start) * 1000.0
        log_voice_tts_response(
            provider=result.provider or self._provider,
            voice=voice or self._voice,
            language=self._language,
            duration_ms=duration_ms,
            text_length=len(text),
            audio_bytes=len(result.audio_bytes),
        )
        return result
