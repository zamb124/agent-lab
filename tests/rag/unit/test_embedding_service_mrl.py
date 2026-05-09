"""MRL-усечение и паддинг до полной размерности для pgvector."""

import pytest

from core.rag.services.embedding_service import EmbeddingService


def test_mrl_pads_to_full_dimension_and_normalizes_prefix() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-4b"],
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


def test_mrl_dense_vector_when_dimension_equals_prefix_length() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-4b"],
        dimension=4,
        mrl_output_dimension=4,
    )
    svc._active_dimension = 8
    out = svc._truncate_vectors([[3.0, 4.0, 9.0, 9.0, 1.0, 1.0, 1.0, 1.0]])
    assert len(out) == 1
    vec = out[0]
    assert len(vec) == 4
    prefix_norm = sum(v * v for v in vec) ** 0.5
    assert prefix_norm == pytest.approx(1.0)


def test_get_embedding_dimension_returns_storage_column_size() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-4b"],
        dimension=1024,
        mrl_output_dimension=1024,
    )
    assert svc.get_embedding_dimension() == 1024


def test_mrl_legacy_padding_when_dimension_exceeds_prefix() -> None:
    svc = EmbeddingService(
        api_key="k",
        base_url="https://example.com/v1",
        models=["qwen/qwen3-embedding-4b"],
        dimension=4096,
        mrl_output_dimension=512,
    )
    svc._active_dimension = 4096
    src = [float(i % 11) * 0.01 for i in range(4096)]
    out = svc._truncate_vectors([src])
    assert len(out[0]) == 4096
    tail = out[0][:512]
    norm = sum(v * v for v in tail) ** 0.5
    assert norm == pytest.approx(1.0)
    assert out[0][512:] == [0.0] * (4096 - 512)
