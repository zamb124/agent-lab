"""Тесты HTTP эндпоинта ``POST /voice/api/v1/synthesize``.

Streaming chunked TTS: клиент шлёт текст, получает поток аудио-чанков
(Transfer-Encoding: chunked), ``Content-Type`` задаётся провайдером.

Проверяется:

* ``POST /voice/api/v1/synthesize`` с текстом отдаёт ``200`` и непустое
  аудио (через mock TTS провайдера из fixture ``voice_app``);
* если потоковый TTS не отдал ни одного чанка — ``502``, без ``200`` с пустым телом;
* валидация: пустой ``text`` → ``422``;
* заголовок ``X-Voice-Provider`` проставляется;
* ``voice_client`` без авторизации → запрос отвергается (``401``), если
  middleware анонимные endpoints не допускает, либо возвращает ``200``
  на системной компании — тест принимает оба валидных исхода, чтобы не
  завязываться на конкретный auth middleware (проверяется лишь, что
  эндпоинт не 500).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient

from core.clients.tts_streaming import BaseTTSStreamer


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
    content_type = response.headers.get("content-type", "")
    assert content_type.startswith("audio/"), f"expected audio/* got {content_type!r}"
    assert response.headers.get("x-voice-provider", "") == "mock"
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
    assert response.headers.get("content-type", "").startswith("audio/")
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
        def provider(self) -> str:
            return "silent_test"

        @property
        def mime_type(self) -> str:
            return "audio/wav"

        @property
        def sample_rate(self) -> int:
            return 8000

        async def synthesize_chunk(self, text: str) -> bytes:
            raise RuntimeError("_SilentStreamer does not use synthesize_chunk")

        async def astream(self, text_stream: AsyncIterator[str]) -> AsyncIterator[bytes]:
            async for _ in text_stream:
                pass
            if False:
                yield b""

    async def _fake_get_tts_streamer(*_a: object, **_k: object) -> _SilentStreamer:
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
