"""E2E: голосовой чат через voice-gateway + flows (mock LLM).

Сценарий проверяет **чистую архитектуру** (voice.mdc, speech_providers.mdc,
integrations.mdc):

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

import pytest
from fastapi.testclient import TestClient


@pytest.mark.e2e
def test_voice_chat_e2e_speak_roundtrip(voice_app, unique_id: str) -> None:
    """speak от клиента → PCM из mock TTS + tts_state переключается."""
    with TestClient(voice_app) as client:
        url = (
            f"/voice/api/ws/session/e2e-{unique_id}"
            "?company_id=system"
        )
        with client.websocket_connect(url) as ws:
            media_cfg = None
            for _ in range(10):
                msg = ws.receive()
                text = msg.get("text")
                if text is None:
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
                msg = ws.receive()
                if msg.get("bytes"):
                    saw_pcm = True
                text = msg.get("text")
                if text:
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
                msg = ws.receive()
                text = msg.get("text")
                if text:
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
    voice_app, unique_id: str
) -> None:
    """Клиентский uplink PCM принимается без ошибок.

    В production ``stt_worker`` накопит буфер и вызовет STT-callback.
    Mock STT не выдаёт транскрипт на «пустые» PCM-кадры — тест лишь
    подтверждает, что binary frame path не падает и сессия остаётся
    живой (последующий ``speak`` всё ещё работает).
    """
    with TestClient(voice_app) as client:
        url = (
            f"/voice/api/ws/session/pcm-{unique_id}"
            "?company_id=system"
        )
        with client.websocket_connect(url) as ws:
            for _ in range(10):
                msg = ws.receive()
                text = msg.get("text")
                if text and json.loads(text).get("type") == "media_config":
                    break

            silence_frame = b"\x00" * 640
            for _ in range(5):
                ws.send_bytes(silence_frame)

            ws.send_text(
                json.dumps({"type": "speak", "text": "После PCM ещё работает."})
            )
            saw_playing = False
            for _ in range(60):
                msg = ws.receive()
                text = msg.get("text")
                if text:
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
