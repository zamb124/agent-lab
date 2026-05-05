"""``resolve_rag_provider_bundle`` отдаёт каноничный ``base_url`` эмбеддингов по ``rag.embedding.provider``."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.config.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    LLMConfig,
    ProviderLitserveApiConfig,
    ProviderLitserveConfig,
    RAGConfig,
    RAGProviderConfig,
)
from core.config.rag_provider_factory import resolve_rag_provider_bundle
from core.rag.embedding_runtime import resolve_rag_embedding_runtime


def _minimal_settings(
    *,
    embedding: EmbeddingConfig,
    provider_litserve: ProviderLitserveConfig,
    llm: LLMConfig | None = None,
) -> SimpleNamespace:
    rag = RAGConfig(
        enabled=True,
        default_provider="pgvector",
        embedding=embedding,
        providers={"pgvector": RAGProviderConfig(enabled=True)},
    )
    return SimpleNamespace(
        rag=rag,
        llm=llm if llm is not None else LLMConfig(),
        provider_litserve=provider_litserve,
    )


def test_resolve_rag_provider_bundle_litserve_uses_resolved_v1_base() -> None:
    lit = ProviderLitserveConfig(api=ProviderLitserveApiConfig(base_url="http://127.0.0.1:8014/v1"))
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(model="qwen/qwen3-embedding-8b", dimension=4096, base_url=None),
    )
    settings = _minimal_settings(embedding=emb, provider_litserve=lit)
    bundle = resolve_rag_provider_bundle(settings)
    assert bundle.embedding_runtime is not None
    assert bundle.embedding_runtime["provider"] == "provider_litserve"
    assert bundle.embedding_runtime["base_url"] == "http://127.0.0.1:8014/v1"
    assert bundle.embedding_runtime["model"] == "qwen/qwen3-embedding-8b"
    assert bundle.embedding_runtime["dimension"] == 4096


def test_resolve_rag_embedding_runtime_litserve_prefers_embedding_api_base_url() -> None:
    lit = ProviderLitserveConfig(api=ProviderLitserveApiConfig(base_url="http://127.0.0.1:8014/v1"))
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(
            model="qwen/qwen3-embedding-8b",
            dimension=4096,
            base_url="http://192.168.1.2:8014/v1",
        ),
    )
    rt = resolve_rag_embedding_runtime(emb, LLMConfig(), lit)
    assert rt.base_url == "http://192.168.1.2:8014/v1"


def test_resolve_rag_embedding_runtime_litserve_requires_root_when_api_base_url_empty() -> None:
    lit = ProviderLitserveConfig(api=ProviderLitserveApiConfig(base_url=None))
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(model="qwen/qwen3-embedding-8b", dimension=4096, base_url=None),
    )
    with pytest.raises(ValueError, match="provider_litserve.api.base_url"):
        resolve_rag_embedding_runtime(emb, LLMConfig(), lit)

