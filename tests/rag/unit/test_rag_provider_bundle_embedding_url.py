"""``resolve_rag_provider_bundle`` отдаёт каноничный ``base_url`` эмбеддингов по ``rag.embedding.provider``."""

from __future__ import annotations

from core.config.base import BaseSettings
from core.config.models import (
    EmbeddingApiConfig,
    EmbeddingConfig,
    LLMConfig,
    RAGConfig,
    RAGProviderConfig,
    ServerConfig,
)
from core.config.rag_provider_factory import resolve_rag_provider_bundle
from core.rag.embedding_runtime import resolve_rag_embedding_runtime


def _minimal_settings(
    *,
    embedding: EmbeddingConfig,
    server: ServerConfig | None = None,
    llm: LLMConfig | None = None,
) -> BaseSettings:
    rag = RAGConfig(
        enabled=True,
        default_provider="pgvector",
        embedding=embedding,
        providers={"pgvector": RAGProviderConfig(enabled=True)},
    )
    return BaseSettings(
        rag=rag,
        llm=llm if llm is not None else LLMConfig(),
        server=server if server is not None else ServerConfig(),
    )


def test_resolve_rag_provider_bundle_litserve_uses_canonical_service_url() -> None:
    server = ServerConfig(
        provider_litserve_service_url="http://127.0.0.1:8014"
    )
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(model="qwen/qwen3-embedding-0.6b", dimension=1024, base_url=None, mrl_output_dimension=1024),
    )
    settings = _minimal_settings(embedding=emb, server=server)
    bundle = resolve_rag_provider_bundle(settings)
    assert bundle.embedding_runtime is not None
    assert bundle.embedding_runtime.provider == "provider_litserve"
    assert bundle.embedding_runtime.base_url == "http://127.0.0.1:8014/v1"
    assert bundle.embedding_runtime.model == "qwen/qwen3-embedding-0.6b"
    assert bundle.embedding_runtime.dimension == 1024


def test_resolve_rag_embedding_runtime_litserve_prefers_embedding_api_base_url() -> None:
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(
            model="qwen/qwen3-embedding-0.6b",
            dimension=1024,
            base_url="http://192.168.1.2:8014/v1",
            mrl_output_dimension=1024,
        ),
    )
    rt = resolve_rag_embedding_runtime(emb, LLMConfig(), "http://127.0.0.1:8014/v1")
    assert rt.base_url == "http://192.168.1.2:8014/v1"


def test_resolve_rag_embedding_runtime_litserve_falls_back_to_canonical_url() -> None:
    emb = EmbeddingConfig(
        provider="provider_litserve",
        api=EmbeddingApiConfig(model="qwen/qwen3-embedding-0.6b", dimension=1024, base_url=None, mrl_output_dimension=1024),
    )
    rt = resolve_rag_embedding_runtime(emb, LLMConfig(), "http://provider-litserve:8014/v1")
    assert rt.base_url == "http://provider-litserve:8014/v1"
