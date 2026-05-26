"""
Pydantic-схема ``rag.document_indexing`` (merged ``RAGConfig``): парсинг, нарезка, лексика, дефолты поиска.

Модуль вынесен из ``core.rag``, чтобы не замкнуть импорты с ``core.config``.

Состав ``IndexProfileConfig`` (вложенность = JSON при merge):

    IndexProfileConfig
    ├── parsing: IndexProfileParsingConfig
    ├── split: IndexProfileSplitConfig   (strategy: IndexProfileSplitStrategy)
    ├── lexical: IndexProfileLexicalConfig
    └── search_defaults: IndexProfileSearchDefaults | None
        ├── channels: SearchChannelsDefaults | None
        └── reranker: RerankerSearchDefaults | None

Эмбеддинг в профиле нет: только глобальный ``rag.embedding``.
"""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

__all__ = [
    "IndexProfileConfig",
    "IndexProfileLexicalConfig",
    "IndexProfileParsingConfig",
    "IndexProfileSearchDefaults",
    "IndexProfileSplitConfig",
    "IndexProfileSplitStrategy",
    "RerankerSearchDefaults",
    "SearchChannelsDefaults",
]


# --- Индексация: парсинг ---


class IndexProfileParsingConfig(BaseModel):
    """Движок парсинга и опции, маппящиеся на адаптеры в core/rag/."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    engine: Literal["unstructured", "marker"] = "unstructured"
    languages: list[str] = Field(default_factory=lambda: ["rus", "eng"])


# --- Индексация: нарезка ---


IndexProfileSplitStrategy = Literal[
    "fixed_tokens",
    "semantic",
    "recursive",
    "structure",
    "token",
    "sentence",
    "code",
    "table",
    "fast",
]


class IndexProfileSplitConfig(BaseModel):
    """Параметры нарезки текста на чанки (Chonkie + fixed-token tiktoken strategy)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    strategy: IndexProfileSplitStrategy = "fixed_tokens"
    chunk_size: int = Field(default=512, gt=0)
    chunk_overlap: int = Field(default=50, ge=0)
    chonkie_code_language: str = Field(
        default="auto",
        description="Язык для CodeChunker (auto | python | javascript | ...).",
    )
    chonkie_fast_delimiters: str | None = Field(
        default=None,
        description="Строка-разделители для fast (FastChunker); иначе дефолт Chonkie.",
    )


# --- Индексация: лексический слой ---


class IndexProfileLexicalConfig(BaseModel):
    """Лексический слой по чанкам (FTS/BM25 и т.д.)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = False
    language: str | None = Field(
        default=None,
        description="Язык для tsvector / анализатора, если применимо",
    )


# --- Поиск: дефолты (запрос может переопределить) ---


class SearchChannelsDefaults(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    semantic: bool = True
    lexical: bool = True

    @model_validator(mode="after")
    def at_least_one_channel(self) -> SearchChannelsDefaults:
        if not self.semantic and not self.lexical:
            raise ValueError("Нужен хотя бы один канал: semantic или lexical")
        return self


class RerankerSearchDefaults(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    url: str | None = None
    max_candidates: int | None = Field(default=None, gt=0)


class IndexProfileSearchDefaults(BaseModel):
    """Дефолты поиска (запрос может переопределить)."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    channels: SearchChannelsDefaults | None = None
    rrf_k: int | None = Field(default=None, gt=0)
    per_channel_top_k: int | None = Field(default=None, gt=0)
    default_mode: Literal["fast", "deep"] | None = None
    reranker: RerankerSearchDefaults | None = None


# --- Корень профиля ---


class IndexProfileConfig(BaseModel):
    """
    Полная схема индексации документов (парсинг, split, lexical, search_defaults).

    Поле `embedding` здесь отсутствует — модель эмбеддинга задаётся глобальным ``rag.embedding``.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    split: IndexProfileSplitConfig = Field(default_factory=IndexProfileSplitConfig)
    parsing: IndexProfileParsingConfig = Field(default_factory=IndexProfileParsingConfig)
    lexical: IndexProfileLexicalConfig = Field(default_factory=IndexProfileLexicalConfig)
    search_defaults: IndexProfileSearchDefaults | None = None
