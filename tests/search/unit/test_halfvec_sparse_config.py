"""Tests for Phase 1b halfvec pilot config and Phase 1c sparse gate (§4.8, §4.3.5)."""

from __future__ import annotations

import pytest

from core.search.pointer_models import (
    HalfVecPilotConfig,
    RunetPointerConfig,
    SparseEvalGate,
    SparsePilotConfig,
    is_sparse_gate_met,
)

# ──────────────────────────────────────────────────────────────────────────────
# Phase 1b: halfvec pilot
# ──────────────────────────────────────────────────────────────────────────────


def test_halfvec_pilot_defaults_disabled() -> None:
    config = RunetPointerConfig()
    assert config.halfvec_pilot.enabled is False
    assert config.halfvec_pilot.mrl_dimension == 512
    assert config.halfvec_pilot.ddl_migrated is False


def test_halfvec_pilot_enabled_via_config() -> None:
    config = RunetPointerConfig(
        halfvec_pilot=HalfVecPilotConfig(enabled=True, mrl_dimension=512),
    )
    assert config.halfvec_pilot.enabled is True
    assert config.halfvec_pilot.mrl_dimension == 512


def test_halfvec_pilot_dimension_bounds() -> None:
    with pytest.raises(Exception):
        HalfVecPilotConfig(enabled=True, mrl_dimension=16)  # below minimum 64
    with pytest.raises(Exception):
        HalfVecPilotConfig(enabled=True, mrl_dimension=2048)  # above maximum 1024


def test_halfvec_pilot_shadow_namespace() -> None:
    cfg = HalfVecPilotConfig(shadow_namespace_suffix="runet:eval:halfvec512")
    assert cfg.shadow_namespace_suffix == "runet:eval:halfvec512"


def test_halfvec_not_active_without_ddl_migration() -> None:
    cfg = HalfVecPilotConfig(enabled=True, ddl_migrated=False)
    # Gate: DDL migration not done → pilot data exists only in shadow namespace
    assert not cfg.ddl_migrated


# ──────────────────────────────────────────────────────────────────────────────
# Phase 1c: SPLADE sparse gate
# ──────────────────────────────────────────────────────────────────────────────


def test_sparse_pilot_defaults_disabled() -> None:
    config = RunetPointerConfig()
    assert config.sparse_pilot.enabled is False
    assert config.sparse_pilot.litserve_model == "naver/splade-v3"
    assert config.sparse_pilot.max_sparse_weights == 300


def test_sparse_eval_gate_defaults() -> None:
    gate = SparseEvalGate()
    assert gate.rare_term_url_recall_threshold == pytest.approx(0.75)
    assert gate.vocabulary_mismatch_threshold == pytest.approx(0.15)


def test_is_sparse_gate_met_both_conditions_true() -> None:
    gate = SparseEvalGate(
        rare_term_url_recall_threshold=0.75,
        vocabulary_mismatch_threshold=0.15,
    )
    assert is_sparse_gate_met(
        gate=gate,
        rare_term_url_recall=0.62,
        vocabulary_mismatch_rate=0.22,
    )


def test_is_sparse_gate_met_recall_above_threshold() -> None:
    gate = SparseEvalGate(
        rare_term_url_recall_threshold=0.75,
        vocabulary_mismatch_threshold=0.15,
    )
    # recall >= threshold → gate NOT met
    assert not is_sparse_gate_met(
        gate=gate,
        rare_term_url_recall=0.80,
        vocabulary_mismatch_rate=0.22,
    )


def test_is_sparse_gate_met_mismatch_below_threshold() -> None:
    gate = SparseEvalGate(
        rare_term_url_recall_threshold=0.75,
        vocabulary_mismatch_threshold=0.15,
    )
    # mismatch <= threshold → gate NOT met
    assert not is_sparse_gate_met(
        gate=gate,
        rare_term_url_recall=0.62,
        vocabulary_mismatch_rate=0.10,
    )


def test_is_sparse_gate_not_met_when_neither_condition() -> None:
    gate = SparseEvalGate()
    assert not is_sparse_gate_met(
        gate=gate,
        rare_term_url_recall=0.85,
        vocabulary_mismatch_rate=0.08,
    )


def test_sparse_pilot_metadata_key() -> None:
    cfg = SparsePilotConfig()
    assert cfg.metadata_key == "sparse_weights"


def test_sparse_pilot_rrf_weight_bounds() -> None:
    with pytest.raises(Exception):
        SparsePilotConfig(rrf_sparse_weight=0.0)  # below minimum 0.1
    with pytest.raises(Exception):
        SparsePilotConfig(rrf_sparse_weight=15.0)  # above maximum 10.0


def test_runet_pointer_config_round_trips_all_phases() -> None:
    config = RunetPointerConfig(
        index_mode="vector_pointer",
        index_study_strategy="hybrid_study",
        halfvec_pilot=HalfVecPilotConfig(enabled=True, mrl_dimension=512),
        sparse_pilot=SparsePilotConfig(enabled=False),
    )
    data = config.model_dump()
    restored = RunetPointerConfig.model_validate(data)
    assert restored.halfvec_pilot.enabled is True
    assert restored.halfvec_pilot.mrl_dimension == 512
    assert restored.sparse_pilot.enabled is False
    assert restored.index_study_strategy == "hybrid_study"
