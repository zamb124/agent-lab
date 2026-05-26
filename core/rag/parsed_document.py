"""
Библиотеко-независимый контракт результата парсинга (RAG-30 / RAG_LOGIC_CHANGE.md).

Типы конкретных парсеров (Unstructured Element, Marker AST) за границей адаптеров.
"""

from __future__ import annotations

from typing import ClassVar, Literal, TypeAlias

from pydantic import ConfigDict, Field

from core.models import StrictBaseModel
from core.types import JsonObject

BlockKind: TypeAlias = Literal["paragraph", "heading", "table", "code", "list", "other"]


class ParsedBlock(StrictBaseModel):
    """Логический блок для структурного сплита (опционально)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=False)

    kind: BlockKind
    text: str
    level: int | None = None
    metadata: JsonObject = Field(default_factory=dict)


class ParsedDocument(StrictBaseModel):
    """Каноническое представление документа перед нарезкой на чанки."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=False)

    canonical_text: str
    blocks: list[ParsedBlock] | None = None
    source_metadata: JsonObject = Field(
        default_factory=dict,
        description="Аудит: parser_engine, версия/опции без типов внешних библиотек",
    )
