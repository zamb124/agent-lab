"""ModelCatalog: резолв api_model_id → hf_model_id для STT/TTS/VAD/embedding/rerank.

Без моков и monkeypatch: реальный ``ModelCatalog`` поверх conf-seed
(``ModelCatalog.from_seed``) и ручных ``entries``.
"""

from __future__ import annotations

import pytest

from apps.provider_litserve.catalog import ModelCatalog
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)

pytestmark = pytest.mark.timeout(15)


def _cfg(unique_id: str) -> ProviderLitserveInfraConfig:
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
                api_model_id=f"qwen-tts-{unique_id}",
                hf_model_id="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
                voice="serena",
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


def test_from_seed_resolves_all_kinds(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    assert catalog.hf_model_id("stt", f"gigaam-{unique_id}") == "ai-sage/GigaAM-v3"
    assert catalog.hf_model_id("tts", f"qwen-tts-{unique_id}") == "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice"
    assert catalog.hf_model_id("vad", f"silero-{unique_id}") == "snakers4/silero-vad"


def test_hf_model_id_returns_none_for_unknown_api_id(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    assert catalog.hf_model_id("stt", f"unknown-{unique_id}") is None
    assert catalog.hf_model_id("tts", f"unknown-{unique_id}") is None
    assert catalog.hf_model_id("vad", f"unknown-{unique_id}") is None


def test_find_entry_case_insensitive(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    entry = catalog.find_entry("stt", f"GIGAAM-{unique_id}".upper())
    assert entry is not None
    assert entry.hf_model_id == "ai-sage/GigaAM-v3"


def test_find_typed_returns_typed_entry(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    stt = catalog.find_typed("stt", f"gigaam-{unique_id}")
    assert isinstance(stt, ProviderLitserveSTTModelEntry)
    assert stt.revision == "e2e_rnnt"
    tts = catalog.find_typed("tts", f"qwen-tts-{unique_id}")
    assert isinstance(tts, ProviderLitserveTTSModelEntry)
    vad = catalog.find_typed("vad", f"silero-{unique_id}")
    assert isinstance(vad, ProviderLitserveVADModelEntry)
    assert vad.threshold == pytest.approx(0.5)


def test_from_seed_includes_embedding_and_rerank_pairs(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    emb_ids = catalog.api_model_ids("embedding")
    assert catalog.hf_model_id("embedding", emb_ids[0]) is not None
    rerank_ids = catalog.api_model_ids("rerank")
    assert catalog.hf_model_id("rerank", rerank_ids[0]) is not None


def test_empty_catalog_entries_and_allowed_ids(unique_id):
    catalog = ModelCatalog({})
    assert catalog.entries("stt") == ()
    assert catalog.api_model_ids("stt") == []
    assert catalog.allowed_ids("stt") == frozenset()
    assert catalog.hf_model_id("stt", f"x-{unique_id}") is None


def test_allowed_ids_matches_entries(unique_id):
    catalog = ModelCatalog.from_seed(_cfg(unique_id))
    assert catalog.allowed_ids("stt") == frozenset({f"gigaam-{unique_id}"})
    assert catalog.api_model_ids("stt") == [f"gigaam-{unique_id}"]
