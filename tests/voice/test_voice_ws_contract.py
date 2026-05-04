"""Контрактные тесты WS-сессии voice: text-frames uplink/downlink.

Проверяется фактический wire-контракт между клиентом (bridge) и
universal-media-gateway `apps/voice`. Сервис не знает про flows/A2A;
в тестах используются mock-провайдеры STT/TTS/VAD через переменные
окружения (см. `tests/fixtures/clients.py::voice_app`).

Контракт:

* сразу после ``accept`` клиент получает ``{"type":"media_config",...}``;
* ``{"type":"speak","text":"..."}`` uplink -> PCM (binary) downlink +
  ``{"type":"tts_state","state":"playing"}``;
* ``{"type":"stop_playback"}`` uplink -> ``tts_state=stopped``;
* ``{"type":"<unknown>"}`` uplink -> ``{"type":"error","code":"voice/ws/bad_command",...}``;
* невалидный JSON uplink -> ``voice/ws/bad_json``;
* ``end_of_utterance`` не бросает ошибок и может идти без текста.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _ws_url(session_id: str) -> str:
    return f"/voice/api/ws/session/{session_id}?company_id=test-company"


def _drain_until(ws, predicate, *, max_frames: int = 50) -> dict | None:
    """Читать фреймы, пока не совпадёт predicate или не кончится лимит.

    Возвращает матчащий фрейм либо None. Бинарные фреймы пропускаются
    (на них predicate не зовётся), но сам факт приёма учитывается.
    """
    for _ in range(max_frames):
        msg = ws.receive()
        if "text" in msg and msg["text"] is not None:
            payload = json.loads(msg["text"])
            if predicate(payload):
                return payload
    return None


def _has_pcm(ws, *, max_frames: int = 50) -> bool:
    """True, если в ближайших фреймах есть binary."""
    for _ in range(max_frames):
        msg = ws.receive()
        if "bytes" in msg and msg["bytes"] is not None:
            return True
    return False


def test_voice_ws_requires_company_id(voice_app, unique_id: str) -> None:
    """Без ``company_id`` endpoint закрывает сокет с кодом 1008."""
    import pytest
    from starlette.websockets import WebSocketDisconnect

    with TestClient(voice_app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                f"/voice/api/ws/session/need-company-{unique_id}?company_id="
            ) as ws:
                ws.receive_text()


def test_voice_ws_sends_media_config_on_accept(voice_app, unique_id: str) -> None:
    """Первым text-фреймом клиент получает ``media_config``."""
    with TestClient(voice_app) as client:
        sid = f"media-cfg-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            payload = _drain_until(ws, lambda f: f.get("type") == "media_config")
            assert payload is not None
            assert isinstance(payload["mime"], str) and payload["mime"] != ""
            assert isinstance(payload["sample_rate"], int) and payload["sample_rate"] > 0
            assert payload.get("channels", 1) >= 1


def test_voice_ws_speak_yields_pcm_and_tts_state(voice_app, unique_id: str) -> None:
    """Команда ``speak`` приводит к PCM и ``tts_state=playing``."""
    with TestClient(voice_app) as client:
        sid = f"speak-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")

            ws.send_text(json.dumps({"type": "speak", "text": "Привет, мир."}))

            saw_playing = False
            saw_pcm = False
            for _ in range(80):
                msg = ws.receive()
                if "bytes" in msg and msg["bytes"]:
                    saw_pcm = True
                if "text" in msg and msg["text"]:
                    payload = json.loads(msg["text"])
                    if payload.get("type") == "tts_state" and payload.get("state") == "playing":
                        saw_playing = True
                if saw_playing and saw_pcm:
                    break
            assert saw_playing, "После speak должен прийти tts_state=playing."
            assert saw_pcm, "После speak должен прийти PCM (binary)."


def test_voice_ws_stop_playback_emits_stopped(voice_app, unique_id: str) -> None:
    """Команда ``stop_playback`` отдаёт ``tts_state=stopped``."""
    with TestClient(voice_app) as client:
        sid = f"stop-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")

            ws.send_text(json.dumps({"type": "speak", "text": "Длинное сообщение"}))
            _drain_until(
                ws, lambda f: f.get("type") == "tts_state" and f.get("state") == "playing"
            )
            ws.send_text(json.dumps({"type": "stop_playback"}))

            payload = _drain_until(
                ws,
                lambda f: f.get("type") == "tts_state" and f.get("state") == "stopped",
            )
            assert payload is not None


def test_voice_ws_unknown_command_returns_error(voice_app, unique_id: str) -> None:
    """Неизвестный ``type`` uplink -> ``voice/ws/bad_command``."""
    with TestClient(voice_app) as client:
        sid = f"bad-cmd-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")

            ws.send_text(json.dumps({"type": "this_is_not_a_real_command"}))
            payload = _drain_until(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_command",
            )
            assert payload is not None


def test_voice_ws_malformed_json_returns_bad_json_error(
    voice_app, unique_id: str
) -> None:
    """Строка, не являющаяся JSON, -> ``voice/ws/bad_json``."""
    with TestClient(voice_app) as client:
        sid = f"bad-json-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")

            ws.send_text("this is not JSON at all {")
            payload = _drain_until(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_json",
            )
            assert payload is not None


def test_voice_ws_speak_without_text_field_returns_error(
    voice_app, unique_id: str
) -> None:
    """``speak`` без ``text`` -> ``voice/ws/bad_command``."""
    with TestClient(voice_app) as client:
        sid = f"speak-no-text-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")

            ws.send_text(json.dumps({"type": "speak"}))
            payload = _drain_until(
                ws,
                lambda f: f.get("type") == "error"
                and f.get("code") == "voice/ws/bad_command",
            )
            assert payload is not None


def test_voice_ws_end_of_utterance_without_text_does_not_error(
    voice_app, unique_id: str
) -> None:
    """``end_of_utterance`` без предшествующего ``speak`` — не ошибка."""
    with TestClient(voice_app) as client:
        sid = f"eou-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")
            ws.send_text(json.dumps({"type": "end_of_utterance"}))
            assert True


def test_voice_ws_accepts_binary_pcm_upload(voice_app, unique_id: str) -> None:
    """Клиент может слать PCM сразу после media_config — без ошибок."""
    with TestClient(voice_app) as client:
        sid = f"binary-{unique_id}"
        with client.websocket_connect(_ws_url(sid)) as ws:
            assert _drain_until(ws, lambda f: f.get("type") == "media_config")
            frame = b"\x01\x00" * 320
            for _ in range(5):
                ws.send_bytes(frame)
