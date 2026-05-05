"""MRL-усечение и паддинг до полной размерности для pgvector."""

import pytest

from core.rag.services.embedding_service import EmbeddingService


def test_mrl_pads_to_full_dimension_and_normalizes_prefix() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-8b"],
        dimension=8,
        mrl_output_dimension=2,
    )
    svc._active_dimension = 8
    out = svc._truncate_vectors([[3.0, 4.0, 9.0, 9.0, 9.0, 9.0, 9.0, 9.0]])
    assert len(out) == 1
    vec = out[0]
    assert len(vec) == 8
    prefix_norm = (vec[0] ** 2 + vec[1] ** 2) ** 0.5
    assert prefix_norm == pytest.approx(1.0)
    assert vec[2:] == [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_get_embedding_dimension_uses_full_dimension_with_mrl() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-8b"],
        dimension=4096,
        mrl_output_dimension=512,
    )
    assert svc.get_embedding_dimension() == 4096
