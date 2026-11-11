"""Выбор TTS api_model_id по synthesis_locale (LitServe каталог)."""

from __future__ import annotations

import core.clients.voice_resolver as vr
from core.config.models import ProviderLitserveTTSModelEntry


def test_pick_prefers_matching_synthesis_locale() -> None:
    models = [
        ProviderLitserveTTSModelEntry(
            api_model_id="qwen3-tts-en",
            hf_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            voice="serena",
            sample_rate=24000,
            synthesis_locale="en",
        ),
        ProviderLitserveTTSModelEntry(
            api_model_id="qwen3-tts-es",
            hf_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
            voice="serena",
            sample_rate=24000,
            synthesis_locale="es",
        ),
    ]
    out = vr._pick_tts_api_model_for_synthesis_locale(
        tts_models=models,
        session_locale="es-MX",
        tier_model="qwen3-tts-en",
    )
    assert out == "qwen3-tts-es"


def test_pick_keeps_tier_when_no_locale_match() -> None:
    models = [
        ProviderLitserveTTSModelEntry(
            api_model_id="only-default",
            hf_model_id="snakers4/silero-models",
            silero_bundle="v5_5_ru",
            voice="xenia",
            sample_rate=24000,
        ),
    ]
    out = vr._pick_tts_api_model_for_synthesis_locale(
        tts_models=models,
        session_locale="ru",
        tier_model="only-default",
    )
    assert out == "only-default"


def test_normalize_iso639_1_session_locale() -> None:
    assert vr._normalize_iso639_1_session_locale("ru-RU") == "ru"
    assert vr._normalize_iso639_1_session_locale(None) is None
