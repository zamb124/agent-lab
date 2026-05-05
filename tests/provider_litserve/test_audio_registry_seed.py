"""Сид SQLite-реестра для STT/TTS/VAD: реальная sqlite через tmp_path."""

from __future__ import annotations

import sqlite3

import pytest

from apps.provider_litserve.model_registry import (
    bootstrap_defaults_if_empty,
    create_or_replace_model,
    init_registry,
    list_models,
    sync_defaults_from_config,
)
from core.config.models import (
    ProviderLitserveInfraConfig,
    ProviderLitserveSTTModelEntry,
    ProviderLitserveTTSModelEntry,
    ProviderLitserveVADModelEntry,
)


pytestmark = pytest.mark.timeout(15)


def _cfg(tmp_path, unique_id) -> ProviderLitserveInfraConfig:
    return ProviderLitserveInfraConfig(
        sqlite_path=str(tmp_path / f"registry-{unique_id}.db"),
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


def test_init_registry_creates_models_table_with_audio_kinds(tmp_path, unique_id):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    with sqlite3.connect(cfg.sqlite_path) as conn:
        sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='models'"
        ).fetchone()
        assert sql_row is not None
        sql = sql_row[0]
        for kind in ("llm", "embedding", "rerank", "stt", "tts", "vad"):
            assert f"'{kind}'" in sql, f"kind={kind} отсутствует в CHECK"


def test_bootstrap_seeds_audio_models(tmp_path, unique_id):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    bootstrap_defaults_if_empty(cfg)

    api_ids = {m.api_model_id: m for m in list_models(cfg)}
    assert f"gigaam-{unique_id}" in api_ids
    assert f"silero-tts-{unique_id}" in api_ids
    assert f"silero-{unique_id}" in api_ids

    assert api_ids[f"gigaam-{unique_id}"].kind == "stt"
    assert api_ids[f"gigaam-{unique_id}"].hf_model_id == "ai-sage/GigaAM-v3"
    assert api_ids[f"silero-tts-{unique_id}"].kind == "tts"
    assert api_ids[f"silero-tts-{unique_id}"].hf_model_id == "snakers4/silero-models"
    assert api_ids[f"silero-{unique_id}"].kind == "vad"
    assert api_ids[f"silero-{unique_id}"].hf_model_id == "snakers4/silero-vad"


def test_sync_defaults_is_idempotent_for_audio_kinds(tmp_path, unique_id):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    sync_defaults_from_config(cfg)
    first = list_models(cfg)
    sync_defaults_from_config(cfg)
    second = list_models(cfg)
    assert {m.api_model_id for m in first} == {m.api_model_id for m in second}
    assert len(first) == len(second)


def test_sync_defaults_updates_kind_when_existing_record_has_wrong_kind(
    tmp_path, unique_id
):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    create_or_replace_model(
        cfg,
        kind="llm",
        hf_model_id="x/wrong",
        api_model_id=f"gigaam-{unique_id}",
    )

    sync_defaults_from_config(cfg)

    by_api = {m.api_model_id: m for m in list_models(cfg)}
    record = by_api[f"gigaam-{unique_id}"]
    assert record.kind == "stt"
    assert record.hf_model_id == "ai-sage/GigaAM-v3"
    assert record.status == "ready"


def test_create_or_replace_audio_model_persists(tmp_path, unique_id):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    new_model = create_or_replace_model(
        cfg,
        kind="stt",
        hf_model_id="openai/whisper-large-v3",
        api_model_id=f"whisper-{unique_id}",
    )
    assert new_model.kind == "stt"
    by_api = {m.api_model_id: m for m in list_models(cfg)}
    assert by_api[f"whisper-{unique_id}"].kind == "stt"
    assert by_api[f"whisper-{unique_id}"].hf_model_id == "openai/whisper-large-v3"


def test_unknown_kind_in_create_or_replace_raises(tmp_path, unique_id):
    cfg = _cfg(tmp_path, unique_id)
    init_registry(cfg)
    with pytest.raises(sqlite3.IntegrityError):
        create_or_replace_model(
            cfg,
            kind="audio",  # type: ignore[arg-type]
            hf_model_id="x/y",
            api_model_id=f"x-{unique_id}",
        )
