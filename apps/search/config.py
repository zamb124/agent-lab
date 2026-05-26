"""Search service configuration."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.config import BaseSettings
from core.config.loader import load_merged_config

SearchProviderId = Literal["tinyfish", "linkup", "serper", "tavily"]


class SearchTinyFishConfig(BaseModel):
    """TinyFish Search API settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.search.tinyfish.ai")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)


class SearchLinkupConfig(BaseModel):
    """Linkup Search API settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.linkup.so")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)
    depth: Literal["fast", "standard", "deep"] = Field(default="standard")
    output_type: Literal["searchResults"] = Field(default="searchResults")


class SearchSerperConfig(BaseModel):
    """Serper.dev Google Search API settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://google.serper.dev")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)


class SearchTavilyConfig(BaseModel):
    """Tavily Search API settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.tavily.com")
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)
    search_depth: Literal["basic", "advanced"] = Field(default="basic")
    topic: Literal["general", "news", "finance"] = Field(default="general")
    include_answer: bool = Field(default=False)


class SearchIntegrationConfig(BaseModel):
    """Search provider settings."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider_order: list[SearchProviderId] = Field(
        default_factory=lambda: ["tinyfish", "linkup", "serper", "tavily"]
    )
    provider_state_key_prefix: str = Field(default="search:providers", min_length=1)
    available_ttl_seconds: int = Field(default=300, ge=30, le=86_400)
    unavailable_ttl_seconds: int = Field(default=300, ge=30, le=86_400)
    tinyfish: SearchTinyFishConfig = Field(default_factory=SearchTinyFishConfig)
    linkup: SearchLinkupConfig = Field(default_factory=SearchLinkupConfig)
    serper: SearchSerperConfig = Field(default_factory=SearchSerperConfig)
    tavily: SearchTavilyConfig = Field(default_factory=SearchTavilyConfig)

    @field_validator("provider_order")
    @classmethod
    def _provider_order_unique(cls, value: list[SearchProviderId]) -> list[SearchProviderId]:
        seen: set[SearchProviderId] = set()
        out: list[SearchProviderId] = []
        for provider_id in value:
            if provider_id in seen:
                continue
            seen.add(provider_id)
            out.append(provider_id)
        if not out:
            raise ValueError("provider_order must contain at least one provider")
        return out


class SearchSettings(BaseSettings):
    """Root settings for search service."""

    search: SearchIntegrationConfig = Field(default_factory=SearchIntegrationConfig)


_search_settings: SearchSettings | None = None


def get_search_settings() -> SearchSettings:
    global _search_settings
    if _search_settings is None:
        merged = load_merged_config(service_name="search", silent=True)
        _search_settings = SearchSettings.model_validate(merged)
    return _search_settings


def reset_search_settings() -> None:
    global _search_settings
    _search_settings = None
