"""Typed contracts for web meta-search."""

from __future__ import annotations

from typing import ClassVar, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, field_validator

SearchMode = Literal["quick", "deep", "research"]
SearchSuggestionKind = Literal[
    "refine",
    "follow_up",
    "source_check",
    "compare",
    "deep_dive",
    "research_plan",
]
SearchResultAction = Literal[
    "open_source",
    "summarize_source",
    "ask_source",
    "compare_sources",
    "extract_facts",
]


class WebSearchResult(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    snippet: str = ""
    display_url: str = ""
    provider: str = Field(..., min_length=1)
    provider_rank: int = Field(..., ge=1)
    rank: int = Field(default=0, ge=0)
    score: float = Field(default=0.0, ge=0.0)
    published_at: str | None = None
    source_type: str = Field(default="organic", min_length=1)


class MetaSearchProviderStatus(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    ok: bool
    latency_ms: int = Field(default=0, ge=0)
    results_count: int = Field(default=0, ge=0)
    error: str | None = None
    selected: bool = False
    skipped: bool = False
    skip_reason: str | None = None


class MetaSearchRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=20)
    providers: list[str] = Field(default_factory=lambda: ["auto"])
    provider_strategy: Literal["first_available", "merge"] = "first_available"
    language: str = Field(default="ru", min_length=2, max_length=12)
    region: str = Field(default="ru", min_length=2, max_length=12)
    mode: SearchMode = "quick"

    @field_validator("providers", mode="before")
    @classmethod
    def _normalize_providers(cls, value: object) -> list[str]:
        if value is None:
            return ["auto"]
        if isinstance(value, str):
            raw: list[object] = [value]
        elif isinstance(value, list):
            raw = cast(list[object], value)
        else:
            raise ValueError("providers must be a string or an array")
        out: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ValueError("providers[] must be string")
            provider = item.strip().lower()
            if provider and provider not in out:
                out.append(provider)
        return out or ["auto"]


class MetaSearchResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str
    results: list[WebSearchResult]
    providers: dict[str, MetaSearchProviderStatus]


class SearchSuggestion(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., min_length=1, max_length=300)
    kind: SearchSuggestionKind
    score: float = Field(..., ge=0.0, le=1.0)


class SearchSuggestRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500)
    results: list[WebSearchResult] = Field(default_factory=list, max_length=20)
    mode: SearchMode = "quick"
    language: str = Field(default="ru", min_length=2, max_length=12)
    limit: int = Field(default=6, ge=1, le=10)


class SearchSuggestResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str
    mode: SearchMode
    suggestions: list[SearchSuggestion]
    followups: list[SearchSuggestion]


class SearchResultInsight(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    rank: int = Field(..., ge=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_terms: list[str] = Field(default_factory=list, max_length=12)
    relevance_hint: str = Field(..., min_length=1, max_length=400)
    actions: list[SearchResultAction] = Field(default_factory=list, min_length=1)


class SearchResultInsightsRequest(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str = Field(..., min_length=1, max_length=500)
    results: list[WebSearchResult] = Field(default_factory=list, max_length=20)
    mode: SearchMode = "quick"
    limit: int = Field(default=10, ge=1, le=20)


class SearchResultInsightsResponse(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: str
    mode: SearchMode
    insights: list[SearchResultInsight]
