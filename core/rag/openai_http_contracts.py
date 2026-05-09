"""
Общий контракт OpenAI-совместимого HTTP для RAG-клиентов.

- URL реранка при ``provider_litserve``: ``provider_litserve_rerank_http_url``.
- Клиенты: ``EmbeddingService`` (POST ``.../embeddings``), ``core.rag.post_retrieval_rerank.RerankerHTTPClient``.

Тела запросов и ответы сервера LitServe: ``apps.provider_litserve.openai_server_contracts``.
"""

from __future__ import annotations

from core.config.openai_v1_base_url import normalize_openai_v1_base_url


def provider_litserve_rerank_http_url(openai_v1_base: str) -> str:
    return f"{normalize_openai_v1_base_url(openai_v1_base)}/rerank"
