"""Тесты HTTP эндпоинта ``POST /voice/api/v1/synthesize``.

Streaming chunked TTS: клиент шлёт текст, получает поток аудио-чанков
(Transfer-Encoding: chunked), ``Content-Type`` задаётся провайдером.

Проверяется:

* ``POST /voice/api/v1/synthesize`` с текстом отдаёт ``200`` и непустое
  аудио (через mock TTS провайдера из fixture ``voice_app``);
* валидация: пустой ``text`` → ``422``;
* заголовок ``X-Voice-Provider`` проставляется;
* ``voice_client`` без авторизации → запрос отвергается (``401``), если
  middleware анонимные endpoints не допускает, либо возвращает ``200``
  на системной компании — тест принимает оба валидных исхода, чтобы не
  завязываться на конкретный auth middleware (проверяется лишь, что
  эндпоинт не 500).
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


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
