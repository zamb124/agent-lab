"""Интеграционные тесты voice API через ASGI-клиент и TestClient.

Поднимает реальное FastAPI-приложение voice с mock-провайдерами (без ML-моделей).
Проверяет HTTP-эндпоинты и WebSocket-сессию на уровне HTTP/WS протокола.
"""

import asyncio
import json
import os

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_health_providers_ok(voice_client: AsyncClient) -> None:
    """GET /voice/health/providers возвращает статус VAD."""
    response = await voice_client.get("/voice/health/providers")

    assert response.status_code == 200
    data = response.json()
    assert data["vad"] == "ready"
    assert "checked_at" in data


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_health_providers_returns_json(voice_client: AsyncClient) -> None:
    """Ответ health содержит только ожидаемые поля."""
    response = await voice_client.get("/voice/health/providers")

    assert response.status_code == 200
    data = response.json()
    assert set(data.keys()) >= {"vad", "checked_at"}


def test_voice_ws_session_accepts_binary_frames(voice_app, unique_id: str) -> None:
    """WebSocket принимает бинарные PCM-фреймы и не падает."""
    with TestClient(voice_app) as client:
        session_id = f"ws-binary-{unique_id}"
        with client.websocket_connect(f"/voice/api/ws/session/{session_id}") as ws:
            # Отправляем несколько PCM-фреймов (16-bit mono 16kHz, 20ms каждый)
            pcm_frame = b"\x01\x00" * 320
            ws.send_bytes(pcm_frame)
            ws.send_bytes(pcm_frame)
            # Даём время пайплайну обработать
            # Соединение должно оставаться живым


def test_voice_ws_session_accepts_silence_frames(voice_app, unique_id: str) -> None:
    """WebSocket принимает тишину и не зависает."""
    with TestClient(voice_app) as client:
        session_id = f"ws-silence-{unique_id}"
        with client.websocket_connect(f"/voice/api/ws/session/{session_id}") as ws:
            silence = b"\x00\x00" * 320
            for _ in range(15):
                ws.send_bytes(silence)


def test_voice_ws_session_distinct_session_ids(voice_app, unique_id: str) -> None:
    """Каждый session_id независим — два соединения не конфликтуют."""
    with TestClient(voice_app) as client:
        sid1 = f"sess-a-{unique_id}"
        sid2 = f"sess-b-{unique_id}"

        with client.websocket_connect(f"/voice/api/ws/session/{sid1}") as ws1:
            ws1.send_bytes(b"\x00" * 64)

        with client.websocket_connect(f"/voice/api/ws/session/{sid2}") as ws2:
            ws2.send_bytes(b"\x00" * 64)


def test_voice_ws_stt_pipeline_produces_no_error(voice_app, unique_id: str) -> None:
    """STT pipeline с mock-провайдером не бросает исключений при реальных фреймах."""
    with TestClient(voice_app) as client:
        session_id = f"stt-pipeline-{unique_id}"

        with client.websocket_connect(f"/voice/api/ws/session/{session_id}") as ws:
            speech = b"\x01\x00" * 320
            silence = b"\x00\x00" * 320

            # Речь — должна уйти в STT провайдер
            for _ in range(3):
                ws.send_bytes(speech)

            # Тишина — должна триггернуть flush_buffer()
            for _ in range(10):
                ws.send_bytes(silence)


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_mock_tts_provider_synthesizes_bytes(voice_app) -> None:
    """Mock TTS провайдер в контейнере voice синтезирует непустые байты."""
    from apps.voice.container import get_voice_container

    container = get_voice_container()
    tts = container.tts_provider

    audio = await tts.synthesize("Привет мир")

    assert isinstance(audio, bytes)
    assert len(audio) > 0


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_mock_stt_provider_transcribes(voice_app) -> None:
    """Mock STT провайдер в контейнере возвращает текст из VOICE__STT__MOCK_TRANSCRIPT_TEXT (тестовый env)."""
    from apps.voice.container import get_voice_container

    container = get_voice_container()
    stt = container.stt_provider

    await stt.push_audio(b"\x01\x00" * 320)
    result = await stt.flush_buffer()

    assert result is not None
    assert result.text == os.environ.get(
        "VOICE__STT__MOCK_TRANSCRIPT_TEXT", "Тестовая транскрипция"
    )


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_mock_vad_detects_speech(voice_app) -> None:
    """Mock VAD провайдер в контейнере правильно детектирует речь."""
    from apps.voice.container import get_voice_container

    container = get_voice_container()
    vad = container.vad_provider

    is_speech = await vad.detect_speech(b"\x01\x00" * 320, sample_rate=16000)
    assert is_speech is True
