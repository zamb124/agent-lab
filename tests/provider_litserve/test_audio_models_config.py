"""Pydantic-модели аудио-сущностей в ProviderLitserveInfraConfig.

Без моков и monkeypatch: реальные ``ProviderLitserveInfraConfig``,
``ProviderLitserveSTT/TTS/VADModelEntry``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config.models import (
    EmbeddingConfig,
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
    RerankerRuntimeConfig,
)


pytestmark = pytest.mark.timeout(15)


def test_default_litserve_infra_uses_qwen_embedding_and_rerank(unique_id):
    cfg = ProviderLitserveInfraConfig(sqlite_path=f"./data/test/{unique_id}.db")
    assert cfg.model_id == "Qwen/Qwen3-Reranker-0.6B"
    assert cfg.embedding_model_id == "Qwen/Qwen3-Embedding-0.6B"
    assert cfg.embedding_openai_model_id == "qwen/qwen3-embedding-0.6b"
    assert cfg.rerank_openai_model_id == "qwen/qwen3-reranker-0.6b"
    assert cfg.backend == "flagllm"
    assert cfg.max_length == 8192
    assert cfg.model_batch_size == 4


def test_rag_embedding_config_defaults_litserve_qwen() -> None:
    emb = EmbeddingConfig()
    assert emb.provider == "provider_litserve"
    assert emb.api.model == "qwen/qwen3-embedding-0.6b"
    assert emb.api.dimension == 1024


def test_rag_reranker_runtime_defaults_provider_litserve() -> None:
    rr = RerankerRuntimeConfig()
    assert rr.provider == "provider_litserve"
    assert rr.api is not None


def test_default_stt_entry_has_gigaam_backend_and_revision(unique_id):
    cfg = ProviderLitserveInfraConfig(sqlite_path=f"./data/test/{unique_id}.db")
    assert len(cfg.stt_models) >= 1
    default = next(
        m for m in cfg.stt_models if m.api_model_id == cfg.stt_default_api_model_id
    )
    assert default.backend == "gigaam"
    assert default.hf_model_id == "ai-sage/GigaAM-v3"
    assert default.revision == "e2e_rnnt"


def test_default_tts_entry_has_silero_bundle_voice_sample_rate(unique_id):
    cfg = ProviderLitserveInfraConfig(sqlite_path=f"./data/test/{unique_id}.db")
    default = next(
        m for m in cfg.tts_models if m.api_model_id == cfg.tts_default_api_model_id
    )
    assert default.backend == "silero"
    assert default.hf_model_id == "snakers4/silero-models"
    assert default.silero_bundle == "v5_5_ru"
    assert default.silero_language == "ru"
    assert default.voice == "xenia"
    assert default.synthesis_locale == "ru"
    assert default.sample_rate == 24000
    assert default.tts_input_steps == ("silero_ru_latin_to_cyrillic",)


def test_tts_entry_unknown_input_step_raises(unique_id):
    with pytest.raises(ValidationError, match="неизвестные шаги"):
        ProviderLitserveTTSModelEntry(
            api_model_id=f"t-{unique_id}",
            hf_model_id="snakers4/silero-models",
            silero_bundle="v5_5_ru",
            voice="xenia",
            sample_rate=24000,
            tts_input_steps=("silero_ru_latin_to_cyrillic", "nope"),
        )


def test_tts_entry_empty_input_steps_allowed(unique_id):
    entry = ProviderLitserveTTSModelEntry(
        api_model_id=f"t-{unique_id}",
        hf_model_id="snakers4/silero-models",
        silero_bundle="v5_5_ru",
        voice="xenia",
        sample_rate=24000,
        tts_input_steps=(),
    )
    assert entry.tts_input_steps == ()


def test_default_vad_entry_has_silero_threshold(unique_id):
    cfg = ProviderLitserveInfraConfig(sqlite_path=f"./data/test/{unique_id}.db")
    default = next(
        m for m in cfg.vad_models if m.api_model_id == cfg.vad_default_api_model_id
    )
    assert default.backend == "silero"
    assert default.hf_model_id == "snakers4/silero-vad"
    assert default.sample_rate == 16000
    assert default.threshold == pytest.approx(0.5)


def test_extra_models_in_list_are_kept(unique_id):
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=f"./data/test/{unique_id}.db",
        stt_models=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"gigaam-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
                backend="gigaam",
            ),
            ProviderLitserveSTTModelEntry(
                api_model_id=f"whisper-large-{unique_id}",
                hf_model_id="openai/whisper-large-v3",
                backend="whisper",
            ),
        ],
        stt_default_api_model_id=f"gigaam-{unique_id}",
    )
    api_ids = [m.api_model_id for m in cfg.stt_models]
    assert f"gigaam-{unique_id}" in api_ids
    assert f"whisper-large-{unique_id}" in api_ids


def test_unknown_stt_backend_raises_validation_error(unique_id):
    with pytest.raises(ValidationError):
        ProviderLitserveSTTModelEntry(
            api_model_id=f"x-{unique_id}",
            hf_model_id="x/y",
            backend="not_a_real_backend",  # type: ignore[arg-type]
        )


def test_vad_threshold_out_of_range_raises_validation_error(unique_id):
    with pytest.raises(ValidationError):
        ProviderLitserveVADModelEntry(
            api_model_id=f"v-{unique_id}",
            hf_model_id="x/y",
            sample_rate=16000,
            threshold=2.0,
        )


def test_tts_sample_rate_not_v5_ru_choice_raises_validation_error(unique_id):
    with pytest.raises(ValidationError, match="8000"):
        ProviderLitserveTTSModelEntry(
            api_model_id=f"t-{unique_id}",
            hf_model_id="snakers4/silero-models",
            silero_bundle="v5_5_ru",
            voice="xenia",
            sample_rate=999,
        )


def test_silero_tts_unknown_bundle_raises_validation_error(unique_id):
    with pytest.raises(ValidationError, match="не из поддерживаемых"):
        ProviderLitserveTTSModelEntry(
            api_model_id=f"t-{unique_id}",
            hf_model_id="snakers4/silero-models",
            silero_bundle="not_a_bundle",
            voice="xenia",
            sample_rate=24000,
        )


def test_silero_tts_bundle_whitespace_normalized(unique_id):
    entry = ProviderLitserveTTSModelEntry(
        api_model_id=f"t-{unique_id}",
        hf_model_id="snakers4/silero-models",
        silero_bundle=" V5_5_RU ",
        voice="xenia",
        sample_rate=24000,
    )
    assert entry.silero_bundle == "v5_5_ru"


def test_silero_tts_voice_eugene_invalid_for_v5_4_ru(unique_id):
    with pytest.raises(ValidationError, match="недопустим"):
        ProviderLitserveTTSModelEntry(
            api_model_id=f"t-{unique_id}",
            hf_model_id="snakers4/silero-models",
            silero_bundle="v5_4_ru",
            voice="eugene",
            sample_rate=24000,
        )


def test_extra_field_in_entry_is_forbidden(unique_id):
    with pytest.raises(ValidationError):
        ProviderLitserveSTTModelEntry.model_validate(
            {
                "api_model_id": f"x-{unique_id}",
                "hf_model_id": "x/y",
                "backend": "gigaam",
                "unknown_extra_field": 123,
            }
        )
