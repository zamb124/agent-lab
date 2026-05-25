"""Тесты HTTP эндпоинта ``POST /voice/api/v1/synthesize``.

Streaming chunked TTS: клиент шлёт текст, получает поток аудио-чанков
(Transfer-Encoding: chunked), ``Content-Type`` задаётся провайдером.

Проверяется:

* ``POST /voice/api/v1/synthesize`` с текстом отдаёт ``200`` и непустое
  аудио (через mock TTS провайдера из fixture ``voice_app``);
* если потоковый TTS не отдал ни одного чанка — ``502``, без ``200`` с пустым телом;
* валидация: пустой ``text`` → ``422``;
* заголовок ``X-Voice-Provider`` проставляется;
* ошибка batch TTS от ``provider_litserve`` в форме ``TTSLitserveHttpError``
  (например ``422`` за неверный текст под ru Silero) маппится в тот же HTTP-код
  на ``/synthesize``, не ``500``.
"""

from __future__ import annotations

import io
import wave
from collections.abc import AsyncIterator
from typing import override

import httpx
import pytest
from httpx import AsyncClient

from core.clients.speech_override import SpeechOverride
from core.clients.tts_client import TTSLitserveHttpError
from core.clients.tts_streaming import BaseTTSStreamer
from core.files.media.pcm_to_wav import pcm_s16le_mono_to_wav


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_authenticated_returns_audio_bytes(
    voice_client: AsyncClient, auth_headers_system: dict[str, str]
) -> None:
    """Авторизованный запрос отдаёт непустое аудио через mock TTS."""
    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": "Привет, это тест синтеза речи."},
        headers=auth_headers_system,
    )

    assert response.status_code == 200, response.text
    content_type = response.headers["content-type"]
    assert content_type.startswith("audio/"), f"expected audio/* got {content_type!r}"
    assert response.headers["x-voice-provider"] == "mock"
    audio = response.content
    assert isinstance(audio, (bytes, bytearray)) and len(audio) > 0


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_empty_text_is_rejected(
    voice_client: AsyncClient, auth_headers_system: dict[str, str]
) -> None:
    """Пустой ``text`` блокируется pydantic-валидацией (422)."""
    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": ""},
        headers=auth_headers_system,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_supports_response_format_override(
    voice_client: AsyncClient, auth_headers_system: dict[str, str]
) -> None:
    """Override ``response_format`` уходит в provider (mock возвращает WAV)."""
    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": "Формат по требованию.", "response_format": "wav"},
        headers=auth_headers_system,
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("audio/")
    assert len(response.content) > 0


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_zero_audio_returns_502(
    voice_client: AsyncClient,
    auth_headers_system: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """При отсутствии ненулевых аудио-чанков — 502, не «успешный» пустой ответ."""

    class _SilentStreamer(BaseTTSStreamer):
        @property
        @override
        def provider(self) -> str:
            return "silent_test"

        @property
        @override
        def content_type(self) -> str:
            return "audio/wav"

        @property
        @override
        def sample_rate(self) -> int:
            return 8000

        @override
        async def synthesize_chunk(self, text: str) -> bytes:
            raise RuntimeError("_SilentStreamer does not use synthesize_chunk")

        @override
        async def astream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
            async for piece in text_stream:
                if piece == "\0":
                    yield b""

    async def _fake_get_tts_streamer(
        *, company_id: str, override: SpeechOverride | None = None
    ) -> _SilentStreamer:
        if company_id == "":
            raise AssertionError("company_id must be non-empty")
        _ = override
        return _SilentStreamer()

    monkeypatch.setattr(
        "apps.voice.api.synthesize.get_tts_streamer",
        _fake_get_tts_streamer,
    )

    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": "Текст без аудио в этом тесте."},
        headers=auth_headers_system,
    )

    assert response.status_code == 502, response.text
    body = response.text
    assert "0 байт" in body or "audio" in body.lower(), body


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_litserve_upstream_422_returns_same_detail(
    voice_client: AsyncClient,
    auth_headers_system: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    """Ошибка batch TTS от litserve (например, только латиница под ru Silero) → HTTP 422, не 500."""

    class _Litserve422Streamer(BaseTTSStreamer):
        @property
        @override
        def provider(self) -> str:
            return "litserve"

        @property
        @override
        def content_type(self) -> str:
            return "audio/wav"

        @property
        @override
        def sample_rate(self) -> int:
            return 24000

        @override
        async def synthesize_chunk(self, text: str) -> bytes:
            raise NotImplementedError

        @override
        async def astream(
            self, text_stream: AsyncIterator[str]
        ) -> AsyncIterator[bytes]:
            async for piece in text_stream:
                if piece == "\0":
                    yield b""
                    return
                raise TTSLitserveHttpError(
                    status_code=422,
                    detail=f"litserve-reject-{unique_id}",
                    url="http://127.0.0.1:8014/v1/audio/speech",
                )

    async def _fake_get_tts_streamer(
        *, company_id: str, override: SpeechOverride | None = None
    ) -> _Litserve422Streamer:
        if company_id == "":
            raise AssertionError("company_id must be non-empty")
        _ = override
        return _Litserve422Streamer()

    monkeypatch.setattr(
        "apps.voice.api.synthesize.get_tts_streamer",
        _fake_get_tts_streamer,
    )

    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": f"Latin only {unique_id}"},
        headers=auth_headers_system,
    )

    assert response.status_code == 422, response.text
    assert f"litserve-reject-{unique_id}" in response.text


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_upstream_connect_error_returns_503(
    voice_client: AsyncClient,
    auth_headers_system: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нет TCP к TTS апстриму (ConnectError) — 503 с пояснением, не голый 500 ASGI."""

    class _UnreachableStreamer(BaseTTSStreamer):
        @property
        @override
        def provider(self) -> str:
            return "litserve"

        @property
        @override
        def content_type(self) -> str:
            return "audio/wav"

        @property
        @override
        def sample_rate(self) -> int:
            return 24000

        @override
        async def synthesize_chunk(self, text: str) -> bytes:
            raise NotImplementedError

        @override
        async def astream(
            self, text_stream: AsyncIterator[str]
        ) -> AsyncIterator[bytes]:
            async for piece in text_stream:
                if piece == "\0":
                    yield b""
                    return
                raise httpx.ConnectError("All connection attempts failed")

    async def _fake_get_tts_streamer(
        *, company_id: str, override: SpeechOverride | None = None
    ) -> _UnreachableStreamer:
        if company_id == "":
            raise AssertionError("company_id must be non-empty")
        _ = override
        return _UnreachableStreamer()

    monkeypatch.setattr(
        "apps.voice.api.synthesize.get_tts_streamer",
        _fake_get_tts_streamer,
    )

    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": "Привет без reachable TTS."},
        headers=auth_headers_system,
    )

    assert response.status_code == 503, response.text
    assert "TTS-провайдер недоступен" in response.text


@pytest.mark.asyncio
@pytest.mark.timeout(15)
async def test_synthesize_merges_multi_wav_chunks_into_one_playable_file(
    voice_client: AsyncClient,
    auth_headers_system: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    unique_id: str,
) -> None:
    """Несколько фразовых WAV от astream склеиваются в один RIFF — как ожидает <audio>."""

    w1 = pcm_s16le_mono_to_wav(b"\x03\x00" * 50, sample_rate=16000)
    w2 = pcm_s16le_mono_to_wav(b"\x04\x00" * 70, sample_rate=16000)

    class _MultiWavStreamer(BaseTTSStreamer):
        @property
        @override
        def provider(self) -> str:
            return f"multichunk-{unique_id}"

        @property
        @override
        def content_type(self) -> str:
            return "audio/wav"

        @property
        @override
        def sample_rate(self) -> int:
            return 16000

        @override
        async def synthesize_chunk(self, text: str) -> bytes:
            raise RuntimeError("unused")

        @override
        async def astream(
            self, text_stream: AsyncIterator[str]
        ) -> AsyncIterator[bytes]:
            async for _ in text_stream:
                pass
            yield w1
            yield w2

    async def _fake_get(
        *, company_id: str, override: SpeechOverride | None = None
    ) -> _MultiWavStreamer:
        if company_id == "":
            raise AssertionError("company_id must be non-empty")
        _ = override
        return _MultiWavStreamer()

    monkeypatch.setattr(
        "apps.voice.api.synthesize.get_tts_streamer",
        _fake_get,
    )

    response = await voice_client.post(
        "/voice/api/v1/synthesize",
        json={"text": f"Длинный текст для двух wav. {unique_id}"},
        headers=auth_headers_system,
    )
    assert response.status_code == 200, response.text
    body = response.content
    assert body.startswith(b"RIFF")
    assert body.find(b"RIFF", 4) == -1

    with wave.open(io.BytesIO(body), "rb") as w:
        assert w.getnframes() == 120
