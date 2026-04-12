"""Снимок параметров эмбеддинга для ``indexing_runtime``."""

from core.rag.services.embedding_service import EmbeddingService


def test_runtime_snapshot_after_active_model() -> None:
    svc = EmbeddingService(
        api_key="test-key",
        base_url="https://example.com/v1",
        models=["openai/text-embedding-3-small"],
        dimension=1536,
    )
    svc._active_model = "openai/text-embedding-3-small"
    svc._active_dimension = 1536
    snap = svc.runtime_snapshot(embedding_tokens=42)
    assert {k: snap[k] for k in ("model_used", "embedding_tokens", "provider")} == {
        "model_used": "openai/text-embedding-3-small",
        "embedding_tokens": 42,
        "provider": "openrouter",
    }
    assert "api_url" in snap
