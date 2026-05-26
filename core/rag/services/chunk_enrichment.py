"""
Шаг обогащения чанка (опциональный LLM / контекст для поиска).

Первая поставка (RAG-70): контракт Pydantic + NoOpChunkEnricher без вызова LLM;
результат пишется в metadata_ чанка (`chunk_enrichment`). Эмбеддинг по-прежнему
считается по исходному тексту чанка.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.types import JsonObject


class ChunkEnrichmentContext(StrictBaseModel):
    """Вход одного шага обогащения для одного чанка."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    namespace_id: str
    document_id: str
    document_name: str
    chunk_index: int
    total_chunks: int
    chunk_text: str


class ChunkEnrichmentResult(StrictBaseModel):
    """Выход шага обогащения; при no-op — skipped=True."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    schema_version: int = Field(default=1, ge=1)
    skipped: bool = True
    summary: str | None = None
    extra: JsonObject = Field(default_factory=dict)


@runtime_checkable
class ChunkEnricher(Protocol):
    async def enrich(self, context: ChunkEnrichmentContext) -> ChunkEnrichmentResult:
        ...


class NoOpChunkEnricher:
    """Заглушка без вызова LLM; помечает шаг как пропущенный."""

    async def enrich(self, context: ChunkEnrichmentContext) -> ChunkEnrichmentResult:
        _ = context
        return ChunkEnrichmentResult()
