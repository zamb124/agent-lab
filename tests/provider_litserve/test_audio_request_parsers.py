"""Парсеры тел запросов /v1/audio/* и helper'ы декодирования.

Без моков: реальные функции, реальные PCM-байты, реальный wave-модуль.
"""

from __future__ import annotations

import io
import struct
import wave

import pytest
from fastapi import HTTPException

from apps.provider_litserve.stt.engines import (
    _decode_audio_to_floats,
    parse_stt_body,
)
from apps.provider_litserve.tts.engines import _pcm_to_wav, parse_tts_body
from apps.provider_litserve.vad.engines import parse_vad_body


pytestmark = pytest.mark.timeout(15)


def _generate_pcm16_silence(*, sample_rate: int, duration_s: float) -> bytes:
    n = int(sample_rate * duration_s)
    return struct.pack(f"<{n}h", *([0] * n))


def test_parse_stt_body_uses_default_when_model_omitted(unique_id):
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=0.05)
    parsed = parse_stt_body(
        {"file": pcm}, default_api_model_id=f"gigaam-{unique_id}"
    )
    assert parsed["audio_bytes"] == pcm
    assert parsed["model"] == f"gigaam-{unique_id}"
    assert parsed["language"] is None


def test_parse_stt_body_accepts_explicit_model_and_language(unique_id):
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=0.05)
    parsed = parse_stt_body(
        {"file": pcm, "model": f"whisper-{unique_id}", "language": "en"},
        default_api_model_id=f"gigaam-{unique_id}",
    )
    assert parsed["model"] == f"whisper-{unique_id}"
    assert parsed["language"] == "en"


def test_parse_stt_body_missing_file_raises_422(unique_id):
    with pytest.raises(HTTPException) as exc_info:
        parse_stt_body({}, default_api_model_id=f"gigaam-{unique_id}")
    assert exc_info.value.status_code == 422
    assert "file" in str(exc_info.value.detail)


def test_parse_stt_body_no_default_and_no_model_raises_422():
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=0.05)
    with pytest.raises(HTTPException) as exc_info:
        parse_stt_body({"file": pcm}, default_api_model_id="")
    assert exc_info.value.status_code == 422


def test_parse_tts_body_uses_default_and_normalizes_response_format(unique_id):
    parsed = parse_tts_body(
        {"input": "Привет, мир", "response_format": "FLAC"},
        default_api_model_id=f"kokoro-{unique_id}",
    )
    assert parsed["text"] == "Привет, мир"
    assert parsed["model"] == f"kokoro-{unique_id}"
    assert parsed["voice_override"] is None
    # Неизвестный формат -> wav
    assert parsed["response_format"] == "wav"


def test_parse_tts_body_accepts_voice_and_known_formats(unique_id):
    parsed = parse_tts_body(
        {
            "input": "Тест",
            "model": f"kokoro-{unique_id}",
            "voice": "bf",
            "response_format": "pcm",
        },
        default_api_model_id=f"kokoro-{unique_id}",
    )
    assert parsed["voice_override"] == "bf"
    assert parsed["response_format"] == "pcm"


def test_parse_tts_body_empty_input_raises_value_error(unique_id):
    with pytest.raises(ValueError, match="input"):
        parse_tts_body(
            {"input": "   "}, default_api_model_id=f"kokoro-{unique_id}"
        )


def test_parse_vad_body_default_and_explicit_sample_rate(unique_id):
    pcm = _generate_pcm16_silence(sample_rate=16000, duration_s=0.05)

    parsed_default = parse_vad_body(
        {"audio": pcm}, default_api_model_id=f"silero-{unique_id}"
    )
    assert parsed_default["model"] == f"silero-{unique_id}"
    assert parsed_default["sample_rate_override"] is None

    parsed_explicit = parse_vad_body(
        {"file": pcm, "sample_rate": 8000},
        default_api_model_id=f"silero-{unique_id}",
    )
    assert parsed_explicit["sample_rate_override"] == 8000


def test_parse_vad_body_missing_audio_raises_value_error(unique_id):
    with pytest.raises(ValueError, match="audio"):
        parse_vad_body({}, default_api_model_id=f"silero-{unique_id}")


def test_decode_audio_to_floats_falls_back_to_raw_pcm16():
    pcm = struct.pack("<10h", *([16384] * 10))
    floats, sr = _decode_audio_to_floats(pcm)
    assert sr == 16000
    assert len(floats) == 10
    assert all(abs(v - 0.5) < 0.01 for v in floats)


def test_decode_audio_to_floats_decodes_real_wav_via_soundfile():
    rate = 16000
    n = rate // 2
    samples = [int(8000) for _ in range(n)]
    pcm_bytes = struct.pack(f"<{n}h", *samples)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(pcm_bytes)
    wav_bytes = buf.getvalue()

    floats, sr = _decode_audio_to_floats(wav_bytes)
    assert sr == rate
    assert len(floats) == n
    assert max(floats) > 0.2


def test_decode_audio_to_floats_empty_bytes_raises():
    with pytest.raises(ValueError, match="пустые аудио"):
        _decode_audio_to_floats(b"")


def test_pcm_to_wav_produces_valid_wav_header():
    pcm = struct.pack("<8h", *([4096] * 8))
    wav_bytes = _pcm_to_wav(pcm, sample_rate=24000)
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        assert wf.getframerate() == 24000
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getnframes() == 8


def test_audio_lit_apis_decode_request_annotation_is_fastapi_request():
    """LitServe ожидает аннотацию ``request: fastapi.Request`` в ``decode_request``.

    `litserve.server.LitAPIRequestHandler._prepare_request` именно по этой
    аннотации решает читать body вручную (`await request.json()` /
    `await request.form()`). Любая другая (`Any`, отсутствие — fallback на
    `Request` тоже работает) делегирует валидацию body FastAPI, что для
    больших JSON-тел /v1/audio/* возвращает 422 ещё до `decode_request`.

    Важно: при ``from __future__ import annotations`` в модуле LitAPI
    `inspect.signature(...).parameters["request"].annotation` становится
    строкой ``'Request'`` — сравнение с классом ``Request`` в LitServe ломается,
    в multiprocessing-queue попадает сырой ASGI-``Request`` (pickle → 500,
    ``Can't get local object 'FastAPI.setup.<locals>.openapi'``).
    """
    import inspect
    import typing

    from fastapi import Request

    from apps.provider_litserve.stt.api import STTLitAPI
    from apps.provider_litserve.tts.api import TTSLitAPI
    from apps.provider_litserve.vad.api import VADLitAPI

    for cls in (STTLitAPI, TTSLitAPI, VADLitAPI):
        hints = typing.get_type_hints(cls.decode_request)
        assert hints.get("request") is Request, (
            f"{cls.__name__}.decode_request: ожидался request: fastapi.Request, "
            f"получено {hints.get('request')!r}"
        )
        raw_ann = inspect.signature(cls.decode_request).parameters[
            "request"
        ].annotation
        assert raw_ann is Request, (
            f"{cls.__name__}.decode_request: параметр request должен быть аннотирован "
            f"классом fastapi.Request в runtime (не строкой/ForwardRef): получено {raw_ann!r}"
        )
