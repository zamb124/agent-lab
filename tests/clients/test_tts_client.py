"""Изолированные тесты TTS-клиентов.

Без mocks/monkeypatching: реальный `aiohttp` сервер на свободном порту,
TTS-клиенты ходят туда через настоящий `httpx.AsyncClient`. Stubs
(`YandexTTSClient`, `SberTTSClient`) проверяются на `NotImplementedError`,
`MockTTSClient` — что отдаёт WAV-заглушку.
"""

from __future__ import annotations

import pytest
from aiohttp import web

from core.clients.tts_client import (
    CloudRuTTSClient,
    LitserveTTSClient,
    MockTTSClient,
    SberTTSClient,
    TTSLitserveHttpError,
    TTSResult,
    YandexTTSClient,
)
from core.utils.text_sanitize import sanitize_text_for_speech_backend

from .conftest import FakeSpeechServer

pytestmark = pytest.mark.timeout(15)


def _wav_header(sample_rate: int = 24000) -> bytes:
    return (
        b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
        + sample_rate.to_bytes(4, "little")
        + b"\x80>\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
    )


@pytest.mark.asyncio
async def test_litserve_tts_client_returns_audio_bytes(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    expected_audio = _wav_header() + bytes(range(64))

    async def _handler(request: web.Request) -> web.StreamResponse:
        body = await request.json()
        assert body["model"] == "silero-tts-v5-5-ru"
        assert body["input"] == f"hello {unique_id}"
        assert body["response_format"] == "wav"
        assert body["voice"] == "alloy"
        return web.Response(body=expected_audio, content_type="audio/wav")

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url,
        model="silero-tts-v5-5-ru",
        default_voice="alloy",
        default_response_format="wav",
        default_sample_rate=24000,
        timeout=10.0,
    )
    result = await client.synthesize(text=f"hello {unique_id}")

    assert isinstance(result, TTSResult)
    assert result.provider == "litserve"
    assert result.audio_bytes == expected_audio
    assert result.mime_type == "audio/wav"
    assert result.sample_rate == 24000
    assert result.response_format == "wav"
    assert result.voice == "alloy"
    assert result.model == "silero-tts-v5-5-ru"


@pytest.mark.asyncio
async def test_litserve_tts_client_sends_utf16_sanitized_input(
    fake_speech_server: FakeSpeechServer,
) -> None:
    captured: dict[str, str] = {}

    async def _handler(request: web.Request) -> web.StreamResponse:
        body = await request.json()
        captured["input"] = body["input"]
        return web.Response(body=_wav_header(), content_type="audio/wav")

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    raw = "a" + chr(0xD800) + "b"
    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url,
        model="silero-tts-v5-5-ru",
        default_voice="alloy",
        default_response_format="wav",
        default_sample_rate=24000,
        timeout=10.0,
    )
    await client.synthesize(text=raw)
    assert captured["input"] == sanitize_text_for_speech_backend(raw)


@pytest.mark.asyncio
async def test_litserve_tts_client_sanitizes_voice_in_payload(
    fake_speech_server: FakeSpeechServer,
) -> None:
    captured: dict[str, str] = {}

    async def _handler(request: web.Request) -> web.StreamResponse:
        body = await request.json()
        captured["voice"] = body["voice"]
        return web.Response(body=_wav_header(), content_type="audio/wav")

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url,
        model="silero-tts-v5-5-ru",
        default_voice="alloy\u200b",
        default_response_format="wav",
        default_sample_rate=24000,
        timeout=10.0,
    )
    await client.synthesize(text="hello")
    assert captured["voice"] == "alloy"
    assert "\u200b" not in captured["voice"]


@pytest.mark.asyncio
async def test_litserve_tts_client_http_error_includes_upstream_detail(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    async def _handler(request: web.Request) -> web.StreamResponse:
        assert (await request.json())["model"] == "silero-tts-v5-5-ru"
        return web.json_response({"detail": f"tts-fail-{unique_id}"}, status=500)

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url,
        model="silero-tts-v5-5-ru",
        default_voice="alloy",
        default_response_format="wav",
        default_sample_rate=24000,
        timeout=10.0,
    )
    with pytest.raises(TTSLitserveHttpError, match=f"tts-fail-{unique_id}") as excinfo:
        await client.synthesize(text=f"hello {unique_id}")
    assert excinfo.value.status_code == 500


@pytest.mark.asyncio
async def test_litserve_tts_client_platform_internal_error_appends_log_hint(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    async def _handler(request: web.Request) -> web.StreamResponse:
        _ = await request.json()
        return web.json_response(
            {"detail": "Internal Server Error", "code": "internal_error"},
            status=500,
        )

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url,
        model="silero-tts-v5-5-ru",
        default_voice="alloy",
        default_response_format="wav",
        default_sample_rate=24000,
        timeout=10.0,
    )
    with pytest.raises(TTSLitserveHttpError, match=r"http_unhandled_exception"):
        await client.synthesize(text=f"hello {unique_id}")


@pytest.mark.asyncio
async def test_cloud_ru_tts_client_sends_authorization_and_returns_bytes(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    expected_audio = b"\xfa\xce" + unique_id.encode()

    async def _handler(request: web.Request) -> web.StreamResponse:
        assert request.headers.get("Authorization") == "Bearer cloud-ru-token"
        body = await request.json()
        assert body["voice"] == "alloy"
        assert body["model"] == "openai/tts-1"
        assert body["response_format"] == "mp3"
        return web.Response(body=expected_audio, content_type="audio/mpeg")

    fake_speech_server.route("POST", "/v1/audio/speech", _handler)

    client = CloudRuTTSClient(
        api_key="cloud-ru-token",
        base_url=f"{fake_speech_server.base_url}/v1/audio/speech",
        model="openai/tts-1",
        default_voice="alloy",
        default_response_format="mp3",
        default_sample_rate=24000,
        timeout=10.0,
    )
    result = await client.synthesize(text=f"привет {unique_id}")

    assert result.provider == "cloud_ru"
    assert result.audio_bytes == expected_audio
    assert result.mime_type == "audio/mpeg"
    assert result.response_format == "mp3"


def test_litserve_tts_client_constructor_validation() -> None:
    with pytest.raises(ValueError, match="base_url"):
        LitserveTTSClient(
            base_url="", model="m", default_voice=None,
            default_response_format="wav", default_sample_rate=24000, timeout=1.0,
        )
    with pytest.raises(ValueError, match="model"):
        LitserveTTSClient(
            base_url="http://x", model="", default_voice=None,
            default_response_format="wav", default_sample_rate=24000, timeout=1.0,
        )
    with pytest.raises(ValueError, match="response_format"):
        LitserveTTSClient(
            base_url="http://x", model="m", default_voice=None,
            default_response_format="", default_sample_rate=24000, timeout=1.0,
        )
    with pytest.raises(ValueError, match="sample_rate"):
        LitserveTTSClient(
            base_url="http://x", model="m", default_voice=None,
            default_response_format="wav", default_sample_rate=0, timeout=1.0,
        )
    with pytest.raises(ValueError, match="timeout"):
        LitserveTTSClient(
            base_url="http://x", model="m", default_voice=None,
            default_response_format="wav", default_sample_rate=24000, timeout=0.0,
        )


@pytest.mark.asyncio
async def test_litserve_tts_client_rejects_empty_text(
    fake_speech_server: FakeSpeechServer,
) -> None:
    client = LitserveTTSClient(
        base_url=fake_speech_server.base_url, model="m", default_voice=None,
        default_response_format="wav", default_sample_rate=24000, timeout=10.0,
    )
    with pytest.raises(ValueError, match="пустой text"):
        await client.synthesize(text="")


@pytest.mark.asyncio
async def test_yandex_tts_client_is_stub() -> None:
    client = YandexTTSClient(api_key=None, folder_id=None)
    with pytest.raises(NotImplementedError, match="yandex"):
        await client.synthesize(text="ping")


@pytest.mark.asyncio
async def test_sber_tts_client_is_stub() -> None:
    client = SberTTSClient(client_id=None, client_secret=None, scope="x")
    with pytest.raises(NotImplementedError, match="sber"):
        await client.synthesize(text="ping")


@pytest.mark.asyncio
async def test_mock_tts_client_returns_wav_header(unique_id: str) -> None:
    client = MockTTSClient()
    result = await client.synthesize(text=f"hello {unique_id}")
    assert result.provider == "mock"
    assert result.audio_bytes.startswith(b"RIFF")
    assert result.mime_type == "audio/wav"


@pytest.mark.asyncio
async def test_mock_tts_client_rejects_empty_text() -> None:
    client = MockTTSClient()
    with pytest.raises(ValueError, match="пустой text"):
        await client.synthesize(text="")
