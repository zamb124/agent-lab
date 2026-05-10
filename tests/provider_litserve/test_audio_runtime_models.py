"""runtime_models: резолв api_model_id -> hf_model_id для STT/TTS/VAD.

Без моков и monkeypatch: вызываем реальные функции
``replace_runtime_catalog`` / ``resolve_hf_model_id`` /
``allowed_api_model_ids`` / ``runtime_api_model_ids`` /
``reset_runtime_catalog_for_tests``. Перед каждым тестом autouse-фикстура
в этом модуле сбрасывает каталог, поэтому тесты независимы.
"""

from __future__ import annotations

import pytest

from apps.provider_litserve.runtime_models import (
    allowed_api_model_ids,
    replace_runtime_catalog,
    reset_runtime_catalog_for_tests,
    resolve_hf_model_id,
    runtime_api_model_ids,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)


pytestmark = pytest.mark.timeout(15)


@pytest.fixture(autouse=True)
def _reset_runtime_catalog_autouse() -> None:
    reset_runtime_catalog_for_tests()


def _cfg(unique_id: str) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(
        sqlite_path=f"./data/test/{unique_id}.db",
        stt_models=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"gigaam-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
            ),
        ],
        stt_default_api_model_id=f"gigaam-{unique_id}",
        tts_models=[
            ProviderLitserveTTSModelEntry(
                api_model_id=f"silero-tts-{unique_id}",
                hf_model_id="snakers4/silero-models",
                silero_bundle="v5_5_ru",
                voice="xenia",
                sample_rate=24000,
            ),
        ],
        tts_default_api_model_id=f"silero-tts-{unique_id}",
        vad_models=[
            ProviderLitserveVADModelEntry(
                api_model_id=f"silero-{unique_id}",
                hf_model_id="snakers4/silero-vad",
                sample_rate=16000,
                threshold=0.5,
            ),
        ],
        vad_default_api_model_id=f"silero-{unique_id}",
    )


def test_resolve_uses_default_map_when_runtime_catalog_not_initialized(unique_id):
    cfg = _cfg(unique_id)
    reset_runtime_catalog_for_tests()
    assert resolve_hf_model_id("stt", f"gigaam-{unique_id}", cfg) == "ai-sage/GigaAM-v3"
    assert resolve_hf_model_id("tts", f"silero-tts-{unique_id}", cfg) == "snakers4/silero-models"
    assert resolve_hf_model_id("vad", f"silero-{unique_id}", cfg) == "snakers4/silero-vad"


def test_resolve_returns_none_for_unknown_api_id(unique_id):
    cfg = _cfg(unique_id)
    assert resolve_hf_model_id("stt", f"unknown-{unique_id}", cfg) is None
    assert resolve_hf_model_id("tts", f"unknown-{unique_id}", cfg) is None
    assert resolve_hf_model_id("vad", f"unknown-{unique_id}", cfg) is None


def test_resolve_embedding_and_rerank_fall_back_to_config_when_runtime_initialized_empty(unique_id):
    """Конфиг — источник истины для дефолтных пар RAG; SQLite может отставать после смены model id."""
    cfg = ProviderLitserveInfraConfig(sqlite_path=f"./data/test/{unique_id}.db")
    replace_runtime_catalog([])
    assert resolve_hf_model_id("embedding", cfg.embedding_openai_model_id, cfg) == cfg.embedding_model_id
    assert resolve_hf_model_id("rerank", cfg.rerank_openai_model_id, cfg) == cfg.model_id
    emb_ids = runtime_api_model_ids("embedding", cfg)
    assert cfg.embedding_openai_model_id in emb_ids
    rerank_ids = runtime_api_model_ids("rerank", cfg)
    assert cfg.rerank_openai_model_id in rerank_ids


def test_llm_allowed_and_resolve_merge_config_with_runtime_registry(unique_id):
    """После загрузки SQLite чат/markdown должны видеть и реестр, и llm_model_ids из infra (как embedding/rerank)."""
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=f"./data/test/{unique_id}.db",
        llm_model_ids=["Qwen/Qwen2.5-1.5B-Instruct"],
    )
    replace_runtime_catalog(
        [
            {
                "kind": "llm",
                "api_model_id": f"registry-llm-{unique_id}",
                "hf_model_id": "hf/registry-llm",
            }
        ]
    )
    allowed = allowed_api_model_ids("llm", cfg)
    assert "Qwen/Qwen2.5-1.5B-Instruct" in allowed
    assert f"registry-llm-{unique_id}" in allowed
    assert resolve_hf_model_id("llm", "Qwen/Qwen2.5-1.5B-Instruct", cfg) == "Qwen/Qwen2.5-1.5B-Instruct"
    assert resolve_hf_model_id("llm", f"registry-llm-{unique_id}", cfg) == "hf/registry-llm"


def test_llm_default_map_includes_markdown_default_api_model_id(unique_id):
    """markdown_default_api_model_id должен быть разрешён, даже если не перечислен в llm_model_ids."""
    md_model = f"extra-markdown-only-llm-{unique_id}"
    cfg = ProviderLitserveInfraConfig(
        sqlite_path=f"./data/test/{unique_id}.db",
        llm_model_ids=["Qwen/Qwen2.5-1.5B-Instruct"],
        markdown_default_api_model_id=md_model,
    )
    replace_runtime_catalog([])
    allowed = allowed_api_model_ids("llm", cfg)
    assert md_model in allowed
    assert resolve_hf_model_id("llm", md_model, cfg) == md_model


def test_replace_runtime_catalog_overrides_defaults(unique_id):
    cfg = _cfg(unique_id)
    counts = replace_runtime_catalog(
        [
            {
                "kind": "stt",
                "api_model_id": f"runtime-stt-{unique_id}",
                "hf_model_id": "openai/whisper-large-v3",
            },
            {
                "kind": "tts",
                "api_model_id": f"runtime-tts-{unique_id}",
                "hf_model_id": "x/y-tts",
            },
            {
                "kind": "vad",
                "api_model_id": f"runtime-vad-{unique_id}",
                "hf_model_id": "x/y-vad",
            },
        ]
    )
    assert counts["stt"] == 1
    assert counts["tts"] == 1
    assert counts["vad"] == 1

    assert resolve_hf_model_id("stt", f"runtime-stt-{unique_id}", cfg) == "openai/whisper-large-v3"
    assert resolve_hf_model_id("stt", f"gigaam-{unique_id}", cfg) is None
    assert allowed_api_model_ids("stt", cfg) == frozenset({f"runtime-stt-{unique_id}"})


def test_runtime_api_model_ids_merges_defaults_when_not_initialized(unique_id):
    cfg = _cfg(unique_id)
    ids = runtime_api_model_ids("stt", cfg)
    assert f"gigaam-{unique_id}" in ids


def test_runtime_api_model_ids_uses_only_runtime_when_initialized(unique_id):
    cfg = _cfg(unique_id)
    replace_runtime_catalog(
        [
            {
                "kind": "stt",
                "api_model_id": f"runtime-only-{unique_id}",
                "hf_model_id": "openai/whisper-large-v3",
            }
        ]
    )
    ids = runtime_api_model_ids("stt", cfg)
    assert ids == [f"runtime-only-{unique_id}"]


def test_reset_runtime_catalog_for_tests_returns_to_default_map(unique_id):
    cfg = _cfg(unique_id)
    replace_runtime_catalog(
        [
            {
                "kind": "stt",
                "api_model_id": f"runtime-{unique_id}",
                "hf_model_id": "openai/whisper-large-v3",
            }
        ]
    )
    assert resolve_hf_model_id("stt", f"gigaam-{unique_id}", cfg) is None
    reset_runtime_catalog_for_tests()
    assert resolve_hf_model_id("stt", f"gigaam-{unique_id}", cfg) == "ai-sage/GigaAM-v3"
