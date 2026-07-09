"""Tests for computed platform LLM model scoring."""

from math import isclose

from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.scoring import (
    PlatformModelScoreHint,
    base_catalog_score,
    compute_platform_model_score,
    hint_dimensions_score,
    merge_hint_dimensions,
    split_score_dimensions,
)
from core.config.models import LLMModelScoringConfig


def test_base_catalog_score_uses_model_size_and_context() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/model-120b:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=1_048_576,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        raw={"name": "Vendor 120B"},
    )
    total, breakdown = base_catalog_score(record, AICapability.LLM_CHAT)
    assert total > 50.0
    assert breakdown["catalog_size"] > 0.0
    assert breakdown["catalog_context"] > 0.0
    assert breakdown["catalog_tools"] == 6.0


def test_router_model_scores_low() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="openrouter/free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        is_free=True,
    )
    total, breakdown = base_catalog_score(record, AICapability.LLM_CHAT)
    assert total == 5.0
    assert breakdown["router_fallback"] == 5.0


def test_hint_blend_prefers_configured_dimensions() -> None:
    hint_score, breakdown = hint_dimensions_score(
        {"coding": 96.0, "general_chat": 70.0},
        dimension_weights={"coding": 1.0, "general_chat": 1.0},
    )
    assert hint_score == 83.0
    assert breakdown["hint_blend"] == 83.0


def test_compute_platform_model_score_blends_catalog_and_hints() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="qwen/qwen3-coder:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=1_048_576,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        raw={"name": "Qwen3 Coder 480B"},
    )
    hint = PlatformModelScoreHint(
        editorial_prior=1.0,
        score_dimensions={"coding": 96.0, "general_chat": 70.0},
        enabled=True,
        source="config_seed",
        note=None,
    )
    result = compute_platform_model_score(
        record,
        AICapability.LLM_CHAT,
        hint=hint,
        scoring_config=LLMModelScoringConfig(hint_blend_ratio=0.3),
    )
    assert result.score > 0.0
    assert isclose(result.breakdown["computed_score"], result.score, rel_tol=0.0, abs_tol=1e-4)
    assert result.breakdown["editorial_prior"] == 1.0


def test_split_and_merge_score_dimensions_roundtrip() -> None:
    merged = merge_hint_dimensions(
        2.5,
        {"coding": 95.0, "agentic": 90.0},
    )
    editorial_prior, hints = split_score_dimensions(merged)
    assert editorial_prior == 2.5
    assert hints == {"coding": 95.0, "agentic": 90.0}


def test_non_text_output_gets_modality_penalty() -> None:
    record = AIModelRecord(
        provider="bothub",
        model_id="recraft-v3",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("image",),
        is_free=True,
    )
    total, breakdown = base_catalog_score(record, AICapability.LLM_CHAT)
    assert breakdown["catalog_modality_penalty"] < 0.0
    assert total < 20.0
