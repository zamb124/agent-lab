"""
Библиотеко-независимый контракт результата парсинга (RAG-30 / RAG_LOGIC_CHANGE.md).

Типы конкретных парсеров (Unstructured Element, Marker AST) за границей адаптеров.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BlockKind = Literal["paragraph", "heading", "table", "code", "list", "other"]


class ParsedBlock(BaseModel):
    """Логический блок для структурного сплита (опционально)."""

    model_config = ConfigDict(extra="forbid")

    kind: BlockKind
    text: str
    level: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ParsedDocument(BaseModel):
    """Каноническое представление документа перед нарезкой на чанки."""

    model_config = ConfigDict(extra="forbid")

    canonical_text: str
    blocks: list[ParsedBlock] | None = None
    source_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Аудит: parser_engine, версия/опции без типов внешних библиотек",
    )
