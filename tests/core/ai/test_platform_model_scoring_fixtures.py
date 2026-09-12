"""Offline replay tests for platform LLM scoring on committed catalog fixtures."""

from __future__ import annotations

from math import isclose

import pytest

from core.ai.free_pool import (
    compute_platform_free_record_scores,
    platform_free_records_from_model_records,
)
from core.ai.models import AIModelRecord
from core.ai.providers import AICapability
from core.ai.scoring import PlatformModelScoreOverlay
from core.config import get_settings
from tests.core.ai.scoring_fixture_support import (
    POOL_RANKING_PATH,
    REPLAY_SCORE_TOLERANCE,
    assert_scoring_expectations,
    catalog_by_key,
    load_all_catalog_records,
    load_pool_ranking_snapshot,
    replay_scored_pool_from_fixtures,
)
from tests.core.clients.live_llm_provider_helpers import build_scored_free_pool

pytestmark = pytest.mark.timeout(30)


def test_scoring_fixtures_exist() -> None:
    assert POOL_RANKING_PATH.is_file(), (
        "pool_ranking.json missing — run: uv run python scripts/generate_llm_scoring_fixtures.py"
    )


def test_fixture_replay_scores_match_snapshot() -> None:
    snapshot = load_pool_ranking_snapshot()
    replay_rows = replay_scored_pool_from_fixtures(list(snapshot.providers))
    replay_scores = {row.key: row.score for row in replay_rows}
    assert snapshot.models, "pool_ranking.json models must not be empty"

    for entry in snapshot.models:
        key = (entry.provider, entry.model_id)
        assert key in replay_scores, f"replay missing model {key!r}"
        committed_score = entry.score
        replay_score = replay_scores[key]
        assert isclose(committed_score, replay_score, abs_tol=REPLAY_SCORE_TOLERANCE), (
            f"score mismatch for {key!r}: committed={committed_score}, replay={replay_score}"
        )


def test_fixture_replay_satisfies_expectations() -> None:
    replay_rows = replay_scored_pool_from_fixtures()
    catalog_index = catalog_by_key(load_all_catalog_records())
    assert_scoring_expectations(replay_rows, catalog_index)


def test_disabled_overlay_excludes_model_from_pool() -> None:
    record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/disabled:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        is_free=True,
        free_reason="zero_price_catalog",
    )
    settings = get_settings()
    base_records = platform_free_records_from_model_records([record], settings=settings)
    overlays = {
        ("openrouter", "vendor/disabled:free"): PlatformModelScoreOverlay(
            editorial_prior=0.0,
            enabled=False,
            note=None,
        )
    }
    scored = compute_platform_free_record_scores(
        base_records,
        catalog_records=[record],
        overlays=overlays,
    )
    assert scored == []


def test_unhinted_large_free_model_scores_above_router_fallback() -> None:
    large_record = AIModelRecord(
        provider="openrouter",
        model_id="vendor/large-120b:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        context_length=262144,
        supported_parameters=("tools",),
        is_free=True,
        free_reason="zero_price_catalog",
        raw={"name": "Vendor 120B"},
    )
    router_record = AIModelRecord(
        provider="openrouter",
        model_id="openrouter/free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
        is_free=True,
    )
    settings = get_settings()
    records_by_provider = {
        "openrouter": [large_record, router_record],
    }
    pool = build_scored_free_pool(records_by_provider, settings, providers=("openrouter",))
    scores = {(record.provider, record.id): record.score for record in pool}
    assert scores[("openrouter", "vendor/large-120b:free")] > scores[("openrouter", "openrouter/free")]
