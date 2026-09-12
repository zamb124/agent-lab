"""Tests for computed platform LLM model scoring."""

from math import isclose

import pytest

from core.ai.adapters.catalog_base import BaseModelCatalogAdapter
from core.ai.adapters.openrouter import parse_artificial_analysis_payload
from core.ai.free_pool import (
    compute_platform_free_record_scores,
    platform_free_records_from_model_records,
    sort_platform_free_records,
)
from core.ai.models import AIModelRecord, ArtificialAnalysisIndices
from core.ai.providers import AICapability
from core.ai.scoring import (
    PlatformModelScoreOverlay,
    attach_artificial_analysis,
    catalog_heuristic,
    clamp_editorial_prior,
    compute_platform_model_score,
)
from core.config import get_settings


def test_clamp_editorial_prior_caps_and_keeps_zero() -> None:
    assert clamp_editorial_prior(6) == 5.0
    assert clamp_editorial_prior(-6) == -5.0
    assert clamp_editorial_prior(0) == 0.0
    assert clamp_editorial_prior(1.5) == 1.5


def test_attach_aa_openrouter_does_not_match_last_segment() -> None:
    indices = {
        "someone/other-name": ArtificialAnalysisIndices(
            intelligence_index=88.0,
            model_permaslug="someone/other-name",
        ),
    }
    record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/other-name:free",
        capabilities=(AICapability.LLM_CHAT,),
    )
    attached = attach_artificial_analysis([record], indices)
    assert attached[0].artificial_analysis is None


def test_catalog_heuristic_uses_model_size_and_context() -> None:
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
    total, breakdown = catalog_heuristic(record, AICapability.LLM_CHAT)
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
    total, breakdown = catalog_heuristic(record, AICapability.LLM_CHAT)
    assert total == 5.0
    assert breakdown["router_fallback"] == 5.0


def test_aa_intelligence_beats_heuristic() -> None:
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
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=42.0,
            coding_index=96.0,
            agentic_index=80.0,
            model_permaslug="qwen/qwen3-coder",
        ),
    )
    heuristic, _ = catalog_heuristic(record, AICapability.LLM_CHAT)
    result = compute_platform_model_score(record, AICapability.LLM_CHAT)
    assert result.score == 42.0
    assert result.breakdown["aa_intelligence"] == 42.0
    assert result.score != heuristic
    assert heuristic > 50.0


def test_editorial_prior_adds_to_aa_score() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="qwen/qwen3-coder:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=40.0,
            model_permaslug="qwen/qwen3-coder",
        ),
    )
    result = compute_platform_model_score(
        record,
        AICapability.LLM_CHAT,
        overlay=PlatformModelScoreOverlay(enabled=True, editorial_prior=1.5, note=None),
    )
    assert isclose(result.score, 41.5, abs_tol=1e-9)
    assert result.breakdown["editorial_prior"] == 1.5


def test_equal_aa_uses_catalog_tie_break_not_score() -> None:
    left = AIModelRecord(
        provider="openrouter",
        model_id="vendor/a:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=8000,
        is_free=True,
        free_reason="zero_price_catalog",
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=50.0,
            model_permaslug="vendor/a",
        ),
    )
    right = AIModelRecord(
        provider="openrouter",
        model_id="vendor/b:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=128000,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        artificial_analysis=ArtificialAnalysisIndices(
            intelligence_index=50.0,
            model_permaslug="vendor/b",
        ),
    )
    left_score = compute_platform_model_score(left, AICapability.LLM_CHAT).score
    right_score = compute_platform_model_score(right, AICapability.LLM_CHAT).score
    assert left_score == right_score == 50.0

    ranked = sort_platform_free_records(
        compute_platform_free_record_scores(
            platform_free_records_from_model_records(
                [left, right],
                settings=get_settings(),
            ),
            catalog_records=[left, right],
            overlays=None,
        ),
        max_candidates=10,
    )
    assert [record.id for record in ranked] == ["vendor/b:free", "vendor/a:free"]


def test_no_aa_uses_heuristic() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/model-120b:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=262144,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        raw={"name": "Vendor 120B"},
    )
    result = compute_platform_model_score(record, AICapability.LLM_CHAT)
    heuristic, _ = catalog_heuristic(record, AICapability.LLM_CHAT)
    assert isclose(result.score, heuristic, abs_tol=1e-9)
    assert "aa_intelligence" not in result.breakdown


def test_non_text_output_gets_modality_penalty() -> None:
    record = AIModelRecord(
        provider="bothub",
        model_id="recraft-v3",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("image",),
        is_free=True,
    )
    total, breakdown = catalog_heuristic(record, AICapability.LLM_CHAT)
    assert breakdown["catalog_modality_penalty"] < 0.0
    assert total < 20.0


def test_record_is_free_pricing_or_suffix() -> None:
    assert BaseModelCatalogAdapter._record_is_free(
        {"pricing": {"prompt": "0", "completion": "0"}},
        "vendor/model",
    ) is True
    assert BaseModelCatalogAdapter._record_is_free({}, "vendor/model:free") is True
    assert BaseModelCatalogAdapter._record_is_free(
        {"pricing": {"prompt": "1", "completion": "0"}},
        "vendor/model:free",
    ) is False
    assert BaseModelCatalogAdapter._record_is_free({}, "vendor/model") is None


def test_attach_aa_exact_slug_and_unique_last_segment() -> None:
    indices = {
        "qwen/qwen3-coder": ArtificialAnalysisIndices(
            intelligence_index=70.0,
            model_permaslug="qwen/qwen3-coder",
        ),
        "meta-llama/llama-3.3-70b-instruct": ArtificialAnalysisIndices(
            intelligence_index=55.0,
            model_permaslug="meta-llama/llama-3.3-70b-instruct",
        ),
    }
    openrouter = AIModelRecord(
        provider="openrouter",
        model_id="qwen/qwen3-coder:free",
        capabilities=(AICapability.LLM_CHAT,),
    )
    groq = AIModelRecord(
        provider="groq",
        model_id="llama-3.3-70b-instruct",
        capabilities=(AICapability.LLM_CHAT,),
    )
    attached = attach_artificial_analysis([openrouter, groq], indices)
    assert attached[0].artificial_analysis is not None
    assert attached[0].artificial_analysis.intelligence_index == 70.0
    assert attached[1].artificial_analysis is not None
    assert attached[1].artificial_analysis.intelligence_index == 55.0


def test_attach_aa_does_not_match_ambiguous_last_segment() -> None:
    indices = {
        "vendor-a/shared-name": ArtificialAnalysisIndices(
            intelligence_index=10.0,
            model_permaslug="vendor-a/shared-name",
        ),
        "vendor-b/shared-name": ArtificialAnalysisIndices(
            intelligence_index=90.0,
            model_permaslug="vendor-b/shared-name",
        ),
    }
    groq = AIModelRecord(
        provider="groq",
        model_id="shared-name",
        capabilities=(AICapability.LLM_CHAT,),
    )
    attached = attach_artificial_analysis([groq], indices)
    assert attached[0].artificial_analysis is None


def test_parse_artificial_analysis_skips_rows_without_intelligence() -> None:
    parsed = parse_artificial_analysis_payload(
        {
            "data": [
                {"model_permaslug": "vendor/with-aa", "intelligence_index": 61.5, "coding_index": 40},
                {"model_permaslug": "vendor/no-aa"},
            ]
        }
    )
    assert list(parsed) == ["vendor/with-aa"]
    assert parsed["vendor/with-aa"].intelligence_index == 61.5
    assert parsed["vendor/with-aa"].coding_index == 40.0


def test_parse_artificial_analysis_rejects_duplicate_slug_with_different_score() -> None:
    with pytest.raises(ValueError, match="duplicate model_permaslug"):
        parse_artificial_analysis_payload(
            {
                "data": [
                    {"model_permaslug": "vendor/model", "intelligence_index": 10},
                    {"model_permaslug": "vendor/model", "intelligence_index": 90},
                ]
            }
        )
