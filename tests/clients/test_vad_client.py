"""Изолированные тесты VAD-клиентов.

Без mocks/monkeypatching: для `LitserveVADClient` поднимается реальный
`aiohttp` сервер; `LocalSileroVADClient` пропускается, если пакет
`silero-vad` не установлен (тяжёлая модель тестируется в
`tests/provider_litserve/`).
"""

from __future__ import annotations

import importlib.util

import pytest
from aiohttp import web

from core.clients.vad_client import (
    LitserveVADClient,
    LocalSileroVADClient,
    MockVADClient,
    VADSegment,
)

from .conftest import FakeSpeechServer


pytestmark = pytest.mark.timeout(15)


@pytest.mark.asyncio
async def test_litserve_vad_client_returns_segments(
    fake_speech_server: FakeSpeechServer, unique_id: str
) -> None:
    expected_segments = [
        {"start": 0.1, "end": 0.5},
        {"start": 1.2, "end": 2.0},
    ]

    async def _handler(request: web.Request) -> web.StreamResponse:
        body = await request.json()
        assert body["model"] == "silero-vad-v5"
        assert body["sample_rate"] == 16000
        assert body["threshold"] == 0.6
        assert isinstance(body["audio"], list) and len(body["audio"]) > 0
        return web.json_response({"segments": expected_segments, "trace_id": unique_id})

    fake_speech_server.route("POST", "/v1/audio/vad", _handler)

    client = LitserveVADClient(
        base_url=fake_speech_server.base_url,
        model="silero-vad-v5",
        timeout=10.0,
    )
    segments = await client.detect_segments(
        audio_bytes=b"\x00\x01\x02\x03\x04\x05",
        sample_rate=16000,
        threshold=0.6,
    )
    assert segments == [
        VADSegment(start=0.1, end=0.5),
        VADSegment(start=1.2, end=2.0),
    ]


@pytest.mark.asyncio
async def test_litserve_vad_client_rejects_empty_audio(
    fake_speech_server: FakeSpeechServer,
) -> None:
    client = LitserveVADClient(
        base_url=fake_speech_server.base_url,
        model="silero-vad-v5",
        timeout=10.0,
    )
    with pytest.raises(ValueError, match="audio_bytes"):
        await client.detect_segments(audio_bytes=b"", sample_rate=16000)


def test_litserve_vad_constructor_validates() -> None:
    with pytest.raises(ValueError, match="base_url"):
        LitserveVADClient(base_url="", model="m", timeout=1.0)
    with pytest.raises(ValueError, match="model"):
        LitserveVADClient(base_url="http://x", model="", timeout=1.0)
    with pytest.raises(ValueError, match="timeout"):
        LitserveVADClient(base_url="http://x", model="m", timeout=0.0)


@pytest.mark.asyncio
async def test_mock_vad_client_returns_full_segment_on_input(unique_id: str) -> None:
    client = MockVADClient()
    audio = b"\x10\x00" * 16000  # 1 секунда PCM-16
    segments = await client.detect_segments(audio_bytes=audio, sample_rate=16000)
    assert len(segments) == 1
    seg = segments[0]
    assert seg.start == 0.0
    assert seg.end == pytest.approx(1.0, rel=0.01), f"unique_id={unique_id}"


@pytest.mark.asyncio
async def test_mock_vad_client_returns_empty_for_empty_input() -> None:
    client = MockVADClient()
    segments = await client.detect_segments(audio_bytes=b"", sample_rate=16000)
    assert segments == []


def test_local_silero_vad_constructor_validates() -> None:
    with pytest.raises(ValueError, match="sample_rate"):
        LocalSileroVADClient(sample_rate=0, threshold=0.5)
    with pytest.raises(ValueError, match="threshold"):
        LocalSileroVADClient(sample_rate=16000, threshold=1.5)


@pytest.mark.asyncio
async def test_local_silero_vad_raises_when_package_missing() -> None:
    """Если silero-vad не установлен — RuntimeError при первом вызове."""
    if importlib.util.find_spec("silero_vad") is not None:
        pytest.skip("silero-vad installed; covered by tests/provider_litserve/")
    client = LocalSileroVADClient(sample_rate=16000, threshold=0.5)
    with pytest.raises(RuntimeError, match="silero-vad"):
        await client.detect_segments(
            audio_bytes=b"\x00\x01" * 8000, sample_rate=16000
        )
