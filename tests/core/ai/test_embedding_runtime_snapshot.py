"""Снимок параметров эмбеддинга для ``indexing_runtime``."""

from core.ai.embedding_client import AIEmbeddingClient


def test_runtime_snapshot_uses_configured_model() -> None:
    svc = AIEmbeddingClient(
        api_key="test-key",
        base_url="https://example.com/v1",
        model="openai/text-embedding-3-small",
        dimension=1536,
    )
    snap = svc.runtime_snapshot(embedding_tokens=42)
    assert {k: snap[k] for k in ("model_used", "embedding_tokens", "provider")} == {
        "model_used": "openai/text-embedding-3-small",
        "embedding_tokens": 42,
        "provider": "custom_openai_compatible",
    }
    assert "api_url" in snap
