"""
Параметры привязки RAG namespace к клиенту (поиск, индексация).

Используются ``RAGRepository`` и ``core.rag.rag_resource.RAGResource``.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field

from core.models import StrictBaseModel


class RagResourceBindParams(StrictBaseModel):
    """Namespace, провайдер, поиск и профиль индексации (как у ресурса ``rag`` в flow)."""

    namespace: str = Field(..., description="ID или scope namespace")
    provider: str = Field(default="pgvector", description="RAG провайдер")
    default_top_k: int = Field(default=5, description="Дефолтное количество результатов поиска")
    company_id: Optional[str] = Field(
        default=None,
        description=(
            "Явный X-Company-Id для HTTP-вызовов RAG API (поиск). "
            "Если не задан — из get_context().active_company при выполнении flow."
        ),
    )
    search_options: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Параметры поиска для вызовов search (как у POST /rag/.../search без query, limit, filters): "
            "channels, rrf_k, per_channel_top_k, rerank и пр."
        ),
    )
    index_profile_config: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Частичный профиль индексации (как у IndexProfileConfig): split, parsing, lexical, "
            "опционально search_defaults. Сливается с rag.document_indexing при записи документа."
        ),
    )
