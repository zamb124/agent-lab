"""build_stt/tts/vad_api_pairs + find_*_entry: реальные конфиги, негативные кейсы."""

from __future__ import annotations

import pytest

from apps.provider_litserve.model_registry import (
    build_stt_api_pairs,
    build_tts_api_pairs,
    build_vad_api_pairs,
    find_stt_entry,
    find_tts_entry,
    find_vad_entry,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)


pytestmark = pytest.mark.timeout(15)


def _cfg_with_models(
    *,
    unique_id: str,
    stt: list[ProviderLitserveSTTModelEntry] | None = None,
    stt_default: str | None = None,
    tts: list[ProviderLitserveTTSModelEntry] | None = None,
    tts_default: str | None = None,
    vad: list[ProviderLitserveVADModelEntry] | None = None,
    vad_default: str | None = None,
) -> ProviderLitserveInfraConfig:
    kwargs: dict = {"sqlite_path": f"./data/test/{unique_id}.db"}
    if stt is not None:
        kwargs["stt_models"] = stt
    if stt_default is not None:
        kwargs["stt_default_api_model_id"] = stt_default
    if tts is not None:
        kwargs["tts_models"] = tts
    if tts_default is not None:
        kwargs["tts_default_api_model_id"] = tts_default
    if vad is not None:
        kwargs["vad_models"] = vad
    if vad_default is not None:
        kwargs["vad_default_api_model_id"] = vad_default
    return ProviderLitserveInfraConfig(**kwargs)


def test_stt_pairs_use_api_id_as_key_and_hf_id_as_value(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        stt=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"gigaam-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
            ),
            ProviderLitserveSTTModelEntry(
                api_model_id=f"whisper-{unique_id}",
                hf_model_id="openai/whisper-large-v3",
                backend="whisper",
            ),
        ],
        stt_default=f"gigaam-{unique_id}",
    )
    pairs = build_stt_api_pairs(cfg)
    assert pairs == {
        f"gigaam-{unique_id}": "ai-sage/GigaAM-v3",
        f"whisper-{unique_id}": "openai/whisper-large-v3",
    }


def test_tts_pairs_use_api_id_as_key(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        tts=[
            ProviderLitserveTTSModelEntry(
                api_model_id=f"kokoro-{unique_id}",
                hf_model_id="hexgrad/Kokoro-82M",
                lang="a",
                voice="af_heart",
                sample_rate=24000,
            ),
        ],
        tts_default=f"kokoro-{unique_id}",
    )
    assert build_tts_api_pairs(cfg) == {f"kokoro-{unique_id}": "hexgrad/Kokoro-82M"}


def test_vad_pairs_use_api_id_as_key(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        vad=[
            ProviderLitserveVADModelEntry(
                api_model_id=f"silero-{unique_id}",
                hf_model_id="snakers4/silero-vad",
                sample_rate=16000,
                threshold=0.5,
            ),
        ],
        vad_default=f"silero-{unique_id}",
    )
    assert build_vad_api_pairs(cfg) == {f"silero-{unique_id}": "snakers4/silero-vad"}


def test_default_must_be_present_in_models_list(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        stt=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"gigaam-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
            ),
        ],
        stt_default=f"missing-{unique_id}",
    )
    with pytest.raises(ValueError, match="stt_default_api_model_id"):
        build_stt_api_pairs(cfg)


def test_duplicate_api_model_id_raises(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        stt=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"dup-{unique_id}",
                hf_model_id="x/a",
            ),
            ProviderLitserveSTTModelEntry(
                api_model_id=f"dup-{unique_id}",
                hf_model_id="x/b",
            ),
        ],
        stt_default=f"dup-{unique_id}",
    )
    with pytest.raises(ValueError, match="дубликат api_model_id"):
        build_stt_api_pairs(cfg)


def test_empty_default_raises(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        stt=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"x-{unique_id}",
                hf_model_id="x/y",
            ),
        ],
        stt_default="   ",
    )
    with pytest.raises(ValueError, match="не должен быть пустым"):
        build_stt_api_pairs(cfg)


def test_find_stt_entry_case_insensitive(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        stt=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"GigaAM-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
            ),
        ],
        stt_default=f"GigaAM-{unique_id}",
    )
    found = find_stt_entry(cfg, f"gigaam-{unique_id}")
    assert found is not None
    assert found.revision == "e2e_rnnt"


def test_find_tts_entry_returns_none_for_unknown(unique_id):
    cfg = _cfg_with_models(unique_id=unique_id)
    assert find_tts_entry(cfg, f"never-{unique_id}") is None


def test_find_vad_entry_returns_threshold(unique_id):
    cfg = _cfg_with_models(
        unique_id=unique_id,
        vad=[
            ProviderLitserveVADModelEntry(
                api_model_id=f"silero-{unique_id}",
                hf_model_id="snakers4/silero-vad",
                sample_rate=8000,
                threshold=0.7,
            ),
        ],
        vad_default=f"silero-{unique_id}",
    )
    entry = find_vad_entry(cfg, f"silero-{unique_id}")
    assert entry.threshold == pytest.approx(0.7)
    assert entry.sample_rate == 8000
