"""Юнит-тесты RRF без БД."""

import pytest

from core.rag.rrf import reciprocal_rank_fusion


def test_reciprocal_rank_fusion_two_lists() -> None:
    """RRF объединяет ранги из двух каналов."""
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
    scores = dict(fused)
    assert {
        "b_gt_a": scores["b"] > scores["a"],
        "b_gt_c": scores["b"] > scores["c"],
        "keys": sorted(scores.keys()),
    } == {"b_gt_a": True, "b_gt_c": True, "keys": sorted(["a", "b", "c"])}


def test_reciprocal_rank_fusion_k_must_be_positive() -> None:
    """Недопустимый k — явная ошибка."""
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["x"]], k=0)
