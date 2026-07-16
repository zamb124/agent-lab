"""Tests for eval harness arms and golden set loader."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from apps.search.eval.harness import (
    build_chunking_arm_config,
    list_eval_arm_configs,
    load_golden_queries,
    run_eval_harness,
)
from apps.search.eval.models import EvalRetrievedUrl
from core.search.index_study import CHUNKING_ARM_IDS, list_chunking_arms, list_index_study_arms


def test_chunking_arms_cover_section_13_4() -> None:
    assert set(CHUNKING_ARM_IDS) == {
        "as_is",
        "fixed_512",
        "structure_800",
        "recursive_512",
        "semantic_800",
        "llm_page_meta_only",
    }
    arms = list_chunking_arms()
    assert arms[0].arm_id == "as_is"
    assert arms[0].use_pgvector_default_chunk is True


def test_index_study_arms_registered() -> None:
    study_arms = list_index_study_arms()
    assert {arm.strategy for arm in study_arms} >= {"lexical", "split_embed", "hybrid_study"}


def test_golden_queries_loader() -> None:
    queries = load_golden_queries()
    assert len(queries) >= 30
    rare = [q for q in queries if q.query_type == "rare_term"]
    assert len(rare) >= 20


@pytest.mark.integration
def test_golden_queries_urls_are_reachable() -> None:
    validator = (
        Path(__file__).resolve().parents[3]
        / "apps/search/eval/data/validate_golden_queries.py"
    )
    result = subprocess.run(
        [sys.executable, str(validator)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_list_eval_arm_configs_includes_chunking_and_study() -> None:
    configs = list_eval_arm_configs()
    kinds = {cfg.arm_kind for cfg in configs}
    assert kinds == {"chunking", "index_study"}


@pytest.mark.asyncio
async def test_run_eval_harness_with_stub_search() -> None:
    queries = load_golden_queries()[:3]

    async def search_fn(query: str, limit: int) -> list[EvalRetrievedUrl]:
        _ = query, limit
        return [
            EvalRetrievedUrl(
                url=str(queries[0].relevances[0].url),
                rank=1,
                score=0.99,
            ),
        ]

    arm = build_chunking_arm_config("as_is")
    report = await run_eval_harness(arm=arm, queries=queries, search_fn=search_fn, k=10)
    assert report.arm_id == "as_is"
    assert report.query_count == 3
    assert report.url_recall_at_k > 0
