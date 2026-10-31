"""Seed желаемого состояния каталога: ``build_seed_entries`` для STT/TTS/VAD + RAG."""

from __future__ import annotations

import pytest

from apps.provider_litserve.catalog import (
    build_seed_entries,
    build_vad_seed_entries,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)

pytestmark = pytest.mark.timeout(15)


def _cfg(unique_id) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(
        stt_models=[
            ProviderLitserveSTTModelEntry(
                api_model_id=f"gigaam-{unique_id}",
                hf_model_id="ai-sage/GigaAM-v3",
                revision="e2e_rnnt",
            ),
        ],
        tts_models=[
            ProviderLitserveTTSModelEntry(
                api_model_id=f"silero-tts-{unique_id}",
                hf_model_id="snakers4/silero-models",
                silero_bundle="v5_5_ru",
                voice="xenia",
                sample_rate=24000,
            ),
        ],
        vad_models=[
            ProviderLitserveVADModelEntry(
                api_model_id=f"silero-{unique_id}",
                hf_model_id="snakers4/silero-vad",
                sample_rate=16000,
                threshold=0.5,
            ),
        ],
    )


def test_build_seed_entries_covers_all_five_kinds(unique_id):
    seeds = build_seed_entries(_cfg(unique_id))
    kinds = {kind for kind, _ in seeds}
    assert kinds == {"embedding", "rerank", "stt", "tts", "vad"}


def test_build_seed_entries_keeps_audio_api_ids(unique_id):
    seeds = build_seed_entries(_cfg(unique_id))
    by_kind = {}
    for kind, entry in seeds:
        by_kind.setdefault(kind, {})[entry.api_model_id] = entry.hf_model_id
    assert by_kind["stt"][f"gigaam-{unique_id}"] == "ai-sage/GigaAM-v3"
    assert by_kind["tts"][f"silero-tts-{unique_id}"] == "snakers4/silero-models"
    assert by_kind["vad"][f"silero-{unique_id}"] == "snakers4/silero-vad"


def test_build_seed_entries_includes_default_embedding_and_rerank(unique_id):
    cfg = _cfg(unique_id)
    seeds = build_seed_entries(cfg)
    emb = [e for kind, e in seeds if kind == "embedding"]
    assert any(e.api_model_id == cfg.embedding_openai_model_id for e in emb)
    rerank = [e for kind, e in seeds if kind == "rerank"]
    assert any(e.api_model_id == cfg.rerank_openai_model_id for e in rerank)


def test_vad_seed_rejects_duplicate_api_id(unique_id):
    cfg = _cfg(unique_id)
    dup = ProviderLitserveVADModelEntry(
        api_model_id=f"silero-{unique_id}",
        hf_model_id="x/other",
        sample_rate=8000,
        threshold=0.3,
    )
    cfg = cfg.model_copy(update={"vad_models": [*cfg.vad_models, dup]})
    with pytest.raises(ValueError, match="duplicate api_model_id"):
        build_vad_seed_entries(cfg)
