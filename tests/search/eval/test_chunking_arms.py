"""Tests for chunking arm split configs."""

from __future__ import annotations

from core.search.index_study import get_chunking_arm


def test_structure_800_arm_matches_runet_web_hypothesis() -> None:
    arm = get_chunking_arm("structure_800")
    assert arm.split is not None
    assert arm.split.strategy == "structure"
    assert arm.split.chunk_size == 800
    assert arm.split.chunk_overlap == 120


def test_as_is_arm_uses_pgvector_defaults() -> None:
    arm = get_chunking_arm("as_is")
    assert arm.use_pgvector_default_chunk is True
    assert arm.split is None
