"""
Общий контракт OpenAI-совместимого HTTP для RAG-клиентов.

- URL реранка при ``provider_litserve``: ``provider_litserve_rerank_http_url``.
- Клиенты: ``core.ai.embedding_client.AIEmbeddingClient`` (POST ``.../embeddings``),
  ``core.ai.rerank_client.AIRerankerHTTPClient``.

Тела запросов и ответы сервера LitServe: ``apps.provider_litserve.openai_server_contracts``.
"""

from __future__ import annotations

from core.config.openai_v1_base_url import normalize_openai_v1_base_url

PROVIDER_LITSERVE_PLACEHOLDER_BEARER = "local-litserve"


def provider_litserve_rerank_http_url(openai_v1_base: str) -> str:
    return f"{normalize_openai_v1_base_url(openai_v1_base)}/rerank"
