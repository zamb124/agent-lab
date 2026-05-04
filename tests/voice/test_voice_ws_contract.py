"""Контрактные тесты WS-сессии voice: text-frames uplink/downlink.

Проверяется фактический wire-контракт между клиентом (bridge) и
universal-media-gateway `apps/voice`. Сервис не знает про flows/A2A;
в тестах используются mock-провайдеры STT/TTS/VAD через переменные
окружения (см. `tests/fixtures/clients.py::voice_app`).

Контракт:

* сразу после ``accept`` клиент получает ``{"type":"media_config",...}``;
* ``{"type":"speak","text":"..."}`` uplink → PCM (binary) downlink +
  ``{"type":"tts_state","state":"playing"}``;
* ``{"type":"stop_playback"}`` uplink → ``tts_state=stopped``;
* ``{"type":"<unknown>"}`` uplink → ``{"type":"error","code":"voice/ws/bad_command",...}``;
* невалидный JSON uplink → ``voice/ws/bad_json``;
* ``end_of_utterance`` не бросает ошибок и может идти без текста;
* PCM-кадры binary uplink принимаются без ошибок.

Все проверки объединены в один тест, чтобы не платить за прогрев
FastAPI приложения на каждый ассерт.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def _ws_url(session_id: str) -> str:
    return f"/voice/api/ws/session/{session_id}?company_id=test-company"


def _find_text_frame(ws, predicate, *, max_frames: int = 80) -> dict | None:
    """Читает фреймы и возвращает первый text-JSON, удовлетворяющий predicate."""
    for _ in range(max_frames):
        msg = ws.receive()
        text = msg.get("text")
        if text is None:
            continue
        payload = json.loads(text)
        if predicate(payload):
            return payload
    return None


def test_voice_ws_requires_company_id(voice_app, unique_id: str) -> None:
    """Без ``company_id`` endpoint закрывает сокет с кодом 1008."""
    with TestClient(voice_app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/voice/api/ws/session/need-company-{unique_id}?company_id="
            ) as ws:
                ws.receive_text()


def test_voice_ws_full_text_frame_contract(voice_app, unique_id: str) -> None:
    """Полный контракт text/binary фреймов uplink и downlink.

    Тест намеренно объединяет несколько проверок: каждая отдельная
    ``websocket_connect`` требует startup/shutdown FastAPI-приложения,
    что заметно удлиняет CI. Здесь один сокет проходит через все важные
    состояния wire-контракта.
    """
    with TestClient(voice_app) as client:
        sid = f"contract-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            media_cfg = _find_text_frame(ws, lambda f: f.get("type") == "media_config")
            assert media_cfg is not None
            assert isinstance(media_cfg["mime"], str) and media_cfg["mime"] != ""
            assert (
                isinstance(media_cfg["sample_rate"], int)
                and media_cfg["sample_rate"] > 0
            )
            assert media_cfg.get("channels", 1) >= 1

            ws.send_text(json.dumps({"type": "this_is_not_a_real_command"}))
            unknown_err = _find_text_frame(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_command",
            )
            assert unknown_err is not None

            ws.send_text("this is not JSON at all {")
            bad_json_err = _find_text_frame(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_json",
            )
            assert bad_json_err is not None

            ws.send_text(json.dumps({"type": "speak"}))
            speak_err = _find_text_frame(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_command",
            )
            assert speak_err is not None

            ws.send_text(json.dumps({"type": "end_of_utterance"}))

            frame = b"\x01\x00" * 320
            for _ in range(3):
                ws.send_bytes(frame)

            ws.send_text(
                json.dumps(
                    {"type": "speak", "text": "Это первое тестовое предложение."}
                )
            )

            saw_playing = False
            saw_pcm = False
            for _ in range(120):
                msg = ws.receive()
                if msg.get("bytes"):
                    saw_pcm = True
                text = msg.get("text")
                if text:
                    payload = json.loads(text)
                    if (
                        payload.get("type") == "tts_state"
                        and payload.get("state") == "playing"
                    ):
                        saw_playing = True
                if saw_playing and saw_pcm:
                    break
            assert saw_playing, "После speak должен прийти tts_state=playing."
            assert saw_pcm, "После speak должен прийти PCM (binary)."

            ws.send_text(json.dumps({"type": "stop_playback"}))
            stopped = _find_text_frame(
                ws,
                lambda f: f.get("type") == "tts_state"
                and f.get("state") == "stopped",
            )
            assert stopped is not None
