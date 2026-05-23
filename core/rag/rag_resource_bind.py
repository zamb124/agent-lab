"""
Параметры привязки RAG namespace к клиенту (поиск, индексация).

Используются ``RAGRepository`` и ``core.rag.rag_resource.RAGResource``.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from core.models import StrictBaseModel


class RagResourceBindParams(StrictBaseModel):
    """Namespace, провайдер, поиск и профиль индексации (как у ресурса ``rag`` в flow)."""

    namespace: str = Field(..., description="ID или scope namespace")
    provider: str = Field(default="pgvector", description="RAG провайдер")
    default_top_k: int = Field(default=5, ge=1, description="Дефолтное количество результатов поиска")
    company_id: str | None = Field(
        default=None,
        description=(
            "Явный X-Company-Id для HTTP-вызовов RAG API (поиск). "
            "Если не задан — из get_context().active_company при выполнении flow."
        ),
    )
    search_options: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Параметры поиска для вызовов search (как у POST /rag/.../search без query, limit, filters): "
            "channels, rrf_k, per_channel_top_k, rerank и пр."
        ),
    )
    filters: dict[str, Any] | None = Field(
        default=None,
        description="Дефолтные metadata-фильтры ресурса; call-level filters перекрывают совпадающие ключи.",
    )
    index_profile_config: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Частичный профиль индексации (как у IndexProfileConfig): split, parsing, lexical, "
            "опционально search_defaults. Сливается с rag.document_indexing при записи документа."
        ),
    )


class RagResourceBindPatch(StrictBaseModel):
    """Partial overlay for a shared RAG resource reference."""

    namespace: str | None = Field(default=None, description="ID или scope namespace")
    provider: str | None = Field(default=None, description="RAG провайдер")
    default_top_k: int | None = Field(default=None, ge=1)
    company_id: str | None = None
    search_options: dict[str, Any] | None = None
    filters: dict[str, Any] | None = None
    index_profile_config: dict[str, Any] | None = None
