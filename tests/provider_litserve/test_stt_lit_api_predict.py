"""Контракт ``STTLitAPI.predict`` с циклом LitServe (single vs batched)."""

from __future__ import annotations

from typing import Any

import pytest

from apps.provider_litserve.stt.api import STTLitAPI
from core.config.models import ProviderLitserveInfraConfig

pytestmark = pytest.mark.timeout(15)


class _RecordingEngine:
    """Без TORCH/HF: только фиксирует аргументы ``transcribe_batch``."""

    def __init__(self) -> None:
        self.transcribe_batch_calls: list[list[dict[str, Any]]] = []

    def transcribe_batch(self, items: list[dict[str, Any]]) -> list[str]:
        self.transcribe_batch_calls.append(items)
        return ["ok"] * len(items)


def test_stt_lit_api_predict_wraps_single_decoded_dict() -> None:
    """Single-loop: ``predict`` получает один dict от ``decode_request``, не ``list``."""
    api = STTLitAPI(ProviderLitserveInfraConfig())
    engine = _RecordingEngine()
    api._engine = engine

    sample: dict[str, Any] = {
        "audio_bytes": b"\x00\x01",
        "model": "gigaam-v3-rnnt-ru",
        "language": "ru",
    }
    out = api.predict(sample)
    assert out == ["ok"]
    assert engine.transcribe_batch_calls == [[sample]]


def test_stt_lit_api_predict_passes_list_from_batched_loop() -> None:
    """Batched-loop: после ``decode``+``batch`` в ``predict`` приходит ``list[dict]``."""
    api = STTLitAPI(ProviderLitserveInfraConfig())
    engine = _RecordingEngine()
    api._engine = engine

    a: dict[str, Any] = {
        "audio_bytes": b"a",
        "model": "gigaam-v3-rnnt-ru",
        "language": None,
    }
    b: dict[str, Any] = {
        "audio_bytes": b"b",
        "model": "gigaam-v3-rnnt-ru",
        "language": None,
    }
    out = api.predict([a, b])
    assert out == ["ok", "ok"]
    assert engine.transcribe_batch_calls == [[a, b]]
