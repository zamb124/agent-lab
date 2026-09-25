"""E2E: голосовой чат через voice-gateway + flows (mock LLM).

Сценарий проверяет **чистую архитектуру** (voice.mdc, integrations.mdc):

1. Клиент (эмулятор bridge) открывает WebSocket к universal-media-gateway
   ``/voice/api/ws/session/{id}?company_id=...`` с mock-провайдерами
   STT/TTS/VAD.
2. Клиент посылает text-frame ``{type:"speak", text:"Привет мир."}``
   (как делает клиентский bridge в ответ на speakable A2A-артефакт от
   flows) — voice синтезирует TTS через mock и стримит PCM обратно.
3. Клиент отключается корректно: сессия cancelled без ошибок.

Это *программная* E2E без браузера: Playwright-уровень для
микрофонного аудио в CI нестабилен, а WS-контракт между bridge и
apps/voice в точности тот же, что из web-клиента. Если бы мы
использовали Playwright, контракт был бы тот же — поэтому мы
покрываем именно его. Браузерные тесты shell-ов живут в
``tests/ui/e2e/`` (harness + AppUI) и не дублируют voice/flows wire
ответственность.

Тест смонтирован в ``tests/e2e/voice/`` отдельным пакетом, чтобы не
зависеть от фикстур browser-сессии — использует ``voice_app`` из
``tests/fixtures/clients.py`` (ASGI-транспорт без реального сетевого
стенда).
"""

from __future__ import annotations

import json
from concurrent.futures import CancelledError as FuturesCancelledError
from contextlib import contextmanager, suppress

import pytest
from fastapi.testclient import TestClient


@contextmanager
def _websocket_session(client: TestClient, url: str, cookies: dict[str, str]):
    """Starlette TestClient: при выходе из сессии ``fut.result()`` после cancel даёт ``CancelledError``."""
    cm = client.websocket_connect(url, cookies=cookies)
    ws = cm.__enter__()
    try:
        yield ws
    finally:
        with suppress(FuturesCancelledError):
            cm.__exit__(None, None, None)


def _receive_frame(ws: object) -> dict[str, object]:
    msg = ws.receive()
    if not isinstance(msg, dict):
        raise AssertionError(f"voice websocket frame must be a dict, got {type(msg).__name__}")
    if msg.get("type") == "websocket.close":
        raise AssertionError(
            f"voice websocket closed: code={msg.get('code')} reason={msg.get('reason')}"
        )
    return msg


def _voice_session_url(session_id: str) -> str:
    return (
        f"/voice/api/ws/session/{session_id}"
        "?company_id=system"
        "&stt_provider_name=mock"
        "&tts_provider_name=mock"
        "&vad_provider_name=mock"
    )


@pytest.mark.e2e
def test_voice_chat_e2e_speak_roundtrip(voice_app, unique_id: str, auth_token_system: str) -> None:
    """speak от клиента → PCM из mock TTS + tts_state переключается."""
    with TestClient(voice_app) as client:
        with _websocket_session(
            client,
            _voice_session_url(f"e2e-{unique_id}"),
            {"auth_token": auth_token_system},
        ) as ws:
            media_cfg = None
            for _ in range(10):
                msg = _receive_frame(ws)
                text = msg.get("text")
                if not isinstance(text, str):
                    continue
                payload = json.loads(text)
                if payload.get("type") == "media_config":
                    media_cfg = payload
                    break
            assert media_cfg is not None
            assert media_cfg["mime"].startswith("audio/")
            assert media_cfg["sample_rate"] > 0

            ws.send_text(
                json.dumps(
                    {
                        "type": "speak",
                        "text": "Привет мир это короткое приветствие.",
                    }
                )
            )

            saw_playing = False
            saw_pcm = False
            saw_stopped = False
            for _ in range(120):
                msg = _receive_frame(ws)
                if msg.get("bytes"):
                    saw_pcm = True
                text = msg.get("text")
                if isinstance(text, str):
                    payload = json.loads(text)
                    if payload.get("type") == "tts_state":
                        if payload.get("state") == "playing":
                            saw_playing = True
                        if payload.get("state") == "stopped":
                            saw_stopped = True
                if saw_playing and saw_pcm:
                    break
            assert saw_playing, "speak должен начаться: tts_state=playing"
            assert saw_pcm, "должен прийти PCM (binary) от mock TTS"

            ws.send_text(json.dumps({"type": "stop_playback"}))
            for _ in range(30):
                msg = _receive_frame(ws)
                text = msg.get("text")
                if isinstance(text, str):
                    payload = json.loads(text)
                    if (
                        payload.get("type") == "tts_state"
                        and payload.get("state") == "stopped"
                    ):
                        saw_stopped = True
                        break
            assert saw_stopped, "stop_playback должен вызвать tts_state=stopped"


@pytest.mark.e2e
def test_voice_chat_e2e_binary_pcm_upload_smoke(
    voice_app, unique_id: str, auth_token_system: str
) -> None:
    """Клиентский uplink PCM принимается без ошибок.

    В production ``stt_worker`` накопит буфер и вызовет STT-callback.
    Mock STT не выдаёт транскрипт на «пустые» PCM-кадры — тест лишь
    подтверждает, что binary frame path не падает и сессия остаётся
    живой (последующий ``speak`` всё ещё работает).
    """
    with TestClient(voice_app) as client:
        with _websocket_session(
            client,
            _voice_session_url(f"pcm-{unique_id}"),
            {"auth_token": auth_token_system},
        ) as ws:
            for _ in range(10):
                msg = _receive_frame(ws)
                text = msg.get("text")
                if isinstance(text, str) and json.loads(text).get("type") == "media_config":
                    break

            silence_frame = b"\x00" * 640
            for _ in range(5):
                ws.send_bytes(silence_frame)

            ws.send_text(
                json.dumps({"type": "speak", "text": "После PCM ещё работает."})
            )
            saw_playing = False
            for _ in range(60):
                msg = _receive_frame(ws)
                text = msg.get("text")
                if isinstance(text, str):
                    payload = json.loads(text)
                    if (
                        payload.get("type") == "tts_state"
                        and payload.get("state") == "playing"
                    ):
                        saw_playing = True
                        break
            assert saw_playing, (
                "После uplink PCM сессия обязана продолжать принимать speak"
            )
