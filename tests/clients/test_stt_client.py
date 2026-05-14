"""Изолированные тесты STT-клиентов.

Никаких mocks/monkeypatching: для HTTP-клиентов поднимается реальный
`aiohttp` сервер на свободном порту (`fake_speech_server`), STT-клиенты
дёргают его через настоящий `httpx.AsyncClient`. Для stub-клиентов
(`YandexSTTClient`/`SberSTTClient`) проверяется, что вызов падает с
`NotImplementedError`. Для `MockSTTClient` — что возвращает заданный `transcript_text` конструктора.

`pytestmark = pytest.mark.timeout(15)` — каждый тест укладывается в 15с.
"""

from __future__ import annotations

import pytest
from aiohttp import web

from core.clients.stt_client import (
    CloudRuSTTClient,
    LitserveSTTClient,
    MockSTTClient,
    SberSTTClient,
    STTTranscriptionResult,
    YandexSTTClient,
)
from core.files.models import AudioTranscriptionStatus

from .conftest import FakeSpeechServer

pytestmark = pytest.mark.timeout(15)


@pytest.mark.asyncio
async def test_litserve_stt_client_returns_transcript(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    """LitserveSTTClient: POST /v1/audio/transcriptions → JSON {text}.

    Контракт: тело — JSON `{"model", "language", "file": [int,...]}`,
    `STTLitAPI.parse_stt_body` берёт байты из `raw["file"]` (list[int] →
    `bytes(...)`). Multipart не используется.
    """
    expected_text = f"Привет мир {unique_id}"
    expected_audio = b"\x00\x01\x02\x03"

    async def _handler(request: web.Request) -> web.StreamResponse:
        body = await request.json()
        assert body.get("model") == "gigaam-v3-rnnt-ru"
        assert body.get("language") == "ru"
        assert bytes(body.get("file") or []) == expected_audio
        return web.json_response({"text": expected_text})

    fake_speech_server.route("POST", "/v1/audio/transcriptions", _handler)

    client = LitserveSTTClient(
        base_url=fake_speech_server.base_url,
        model="gigaam-v3-rnnt-ru",
        default_language="ru",
        timeout=10.0,
    )
    result = await client.transcribe_audio(
        audio_bytes=expected_audio,
        file_name=f"audio-{unique_id}.wav",
        mime_type="audio/wav",
    )

    assert isinstance(result, STTTranscriptionResult)
    assert result.provider == "litserve"
    assert result.status == AudioTranscriptionStatus.DONE
    assert result.text == expected_text
    assert result.language == "ru"
    assert len(fake_speech_server.requests) == 1


@pytest.mark.asyncio
async def test_litserve_stt_client_empty_text_means_no_speech(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    """Ответ {text: \"\"} — валидный кейс (нет речи в сегменте), voice worker пропускает."""

    async def _handler(_: web.Request) -> web.StreamResponse:
        return web.json_response({"text": ""})

    fake_speech_server.route("POST", "/v1/audio/transcriptions", _handler)

    client = LitserveSTTClient(
        base_url=fake_speech_server.base_url,
        model="gigaam-v3-rnnt-ru",
        default_language="ru",
        timeout=10.0,
    )
    result = await client.transcribe_audio(
        audio_bytes=b"\x00",
        file_name=f"audio-{unique_id}.wav",
        mime_type="audio/wav",
    )
    assert result.text == ""
    assert result.provider == "litserve"


@pytest.mark.asyncio
async def test_cloud_ru_stt_client_passes_api_key_and_returns_transcript(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    """CloudRuSTTClient: добавляет Authorization: Bearer <key>."""
    expected_text = f"Cloud {unique_id}"

    async def _handler(request: web.Request) -> web.StreamResponse:
        assert request.headers.get("Authorization") == "Bearer test-key"
        form = await request.post()
        assert form.get("language") == "ru"
        return web.json_response({"text": expected_text})

    fake_speech_server.route("POST", "/v1/audio/transcriptions", _handler)

    client = CloudRuSTTClient(
        api_key="test-key",
        base_url=f"{fake_speech_server.base_url}/v1/audio/transcriptions",
        model="cloud-stt",
        response_format="json",
        temperature=0.0,
        default_language="ru",
        timeout=10.0,
    )
    result = await client.transcribe_audio(
        audio_bytes=b"\x00\x01",
        file_name=f"audio-{unique_id}.wav",
        mime_type="audio/wav",
    )

    assert result.provider == "cloud_ru"
    assert result.text == expected_text


def test_litserve_stt_client_validates_constructor() -> None:
    """Конструкторные ValueError при пустых обязательных полях."""
    with pytest.raises(ValueError, match="base_url"):
        LitserveSTTClient(
            base_url="", model="m", default_language="ru", timeout=1.0
        )
    with pytest.raises(ValueError, match="model"):
        LitserveSTTClient(
            base_url="http://x", model="", default_language="ru", timeout=1.0
        )
    with pytest.raises(ValueError, match="language"):
        LitserveSTTClient(
            base_url="http://x", model="m", default_language="", timeout=1.0
        )
    with pytest.raises(ValueError, match="timeout"):
        LitserveSTTClient(
            base_url="http://x", model="m", default_language="ru", timeout=0.0
        )


@pytest.mark.asyncio
async def test_yandex_stt_client_is_stub_until_keys_supplied(unique_id: str) -> None:
    """Stub Yandex STT: любой вызов transcribe_audio → NotImplementedError."""
    client = YandexSTTClient(api_key=None, folder_id=None)
    with pytest.raises(NotImplementedError, match="yandex"):
        await client.transcribe_audio(
            audio_bytes=b"\x00",
            file_name=f"audio-{unique_id}.wav",
            mime_type="audio/wav",
        )


@pytest.mark.asyncio
async def test_sber_stt_client_is_stub_until_keys_supplied(unique_id: str) -> None:
    """Stub Sber STT: любой вызов transcribe_audio → NotImplementedError."""
    client = SberSTTClient(client_id=None, client_secret=None, scope="x")
    with pytest.raises(NotImplementedError, match="sber"):
        await client.transcribe_audio(
            audio_bytes=b"\x00",
            file_name=f"audio-{unique_id}.wav",
            mime_type="audio/wav",
        )


@pytest.mark.asyncio
async def test_mock_stt_client_returns_configured_transcript(unique_id: str) -> None:
    """MockSTTClient возвращает заданный текст и явно валидирует входы."""
    expected_text = f"Тестовая транскрипция {unique_id}"
    client = MockSTTClient(transcript_text=expected_text)
    result = await client.transcribe_audio(
        audio_bytes=b"\x00",
        file_name=f"audio-{unique_id}.wav",
        mime_type="audio/wav",
    )
    assert result.provider == "mock"
    assert result.status == AudioTranscriptionStatus.DONE
    assert result.text == expected_text


def test_mock_stt_client_rejects_empty_transcript_text() -> None:
    with pytest.raises(ValueError, match="transcript_text"):
        MockSTTClient(transcript_text="")
