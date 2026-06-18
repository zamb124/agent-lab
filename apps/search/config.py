"""Platform index search provider configuration and crawl settings."""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.config import BaseSettings
from core.config.loader import get_project_root, load_merged_config
from core.search.index_models import SearchIndexCrawlTaxonomy
from core.types import parse_json_object

SearchProviderId = Literal["tinyfish", "linkup", "serper", "tavily", "index"]


class SearchTinyFishConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.search.tinyfish.ai")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)


class SearchLinkupConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.linkup.so")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)
    depth: Literal["fast", "standard", "deep"] = Field(default="standard")
    output_type: Literal["searchResults"] = Field(default="searchResults")


class SearchSerperConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://google.serper.dev")
    timeout_seconds: float = Field(default=10.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)


class SearchTavilyConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    api_key: str = Field(default="")
    base_url: str = Field(default="https://api.tavily.com")
    timeout_seconds: float = Field(default=15.0, ge=1.0, le=60.0)
    enabled: bool = Field(default=True)
    search_depth: Literal["basic", "advanced"] = Field(default="basic")
    topic: Literal["general", "news", "finance"] = Field(default="general")
    include_answer: bool = Field(default=False)


class SearchIndexProviderConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    enabled: bool = True
    default_index_ids: list[str] = Field(default_factory=lambda: ["runet"])
    max_indexes_per_request: int = Field(default=3, ge=1, le=5)
    registry_cache_ttl_seconds: int = Field(default=60, ge=0, le=300)


class SearchCrawlEnrichmentConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider: str = Field(default="humanitec_llm", min_length=1)
    model: str = Field(default="auto", min_length=1)
    timeout_seconds: float = Field(default=120.0, ge=1.0, le=600.0)
    prompt_version: str = Field(default="structured", min_length=1, max_length=32)
    max_input_chars: int = Field(default=12000, ge=512, le=200_000)


class SearchCrawlConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    default_crawl_profile_id: str = Field(default="runet_platform", min_length=1)
    http_timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)
    sitemap_max_urls_per_domain: int = Field(default=5000, ge=100, le=100_000)
    sitemap_max_bytes: int = Field(default=10_485_760, ge=65_536, le=52_428_800)
    backlog_reschedule_seconds: int = Field(default=300, ge=60, le=3600)
    min_extract_chars: int = Field(default=200, ge=50, le=5000)
    browser_fetch_timeout_seconds: float = Field(default=120.0, ge=30.0, le=300.0)
    tranco_seed_limit: int = Field(default=2000, ge=1, le=5000)
    bootstrap_tranco_on_empty: bool = True
    skip_categories: list[str] = Field(default_factory=lambda: ["ecommerce", "social"])
    ru_com_whitelist: list[str] = Field(
        default_factory=lambda: ["habr.com", "vc.ru", "tass.ru"]
    )
    enrichment: SearchCrawlEnrichmentConfig = Field(default_factory=SearchCrawlEnrichmentConfig)
    taxonomies: dict[str, SearchIndexCrawlTaxonomy] = Field(default_factory=dict)
    taxonomy_files: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _merge_taxonomy_files(self) -> Self:
        if not self.taxonomy_files:
            return self
        project_root = get_project_root()
        merged_taxonomies = dict(self.taxonomies)
        for search_index_id, relative_path in self.taxonomy_files.items():
            index_slug = search_index_id.strip()
            if not index_slug:
                raise ValueError("taxonomy_files key must not be empty")
            taxonomy_path = Path(relative_path.strip())
            if not taxonomy_path.is_absolute():
                taxonomy_path = project_root / taxonomy_path
            taxonomy_payload = parse_json_object(
                taxonomy_path.read_text(encoding="utf-8"),
                f"crawl taxonomy file {taxonomy_path}",
            )
            merged_taxonomies[index_slug] = SearchIndexCrawlTaxonomy.model_validate(taxonomy_payload)
        self.taxonomies = merged_taxonomies
        return self


class SearchIntegrationConfig(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    provider_order: list[SearchProviderId] = Field(
        default_factory=lambda: ["index", "tinyfish", "linkup", "serper", "tavily"]
    )
    provider_state_key_prefix: str = Field(default="search:providers", min_length=1)
    available_ttl_seconds: int = Field(default=300, ge=30, le=86_400)
    unavailable_ttl_seconds: int = Field(default=300, ge=30, le=86_400)
    tinyfish: SearchTinyFishConfig = Field(default_factory=SearchTinyFishConfig)
    linkup: SearchLinkupConfig = Field(default_factory=SearchLinkupConfig)
    serper: SearchSerperConfig = Field(default_factory=SearchSerperConfig)
    tavily: SearchTavilyConfig = Field(default_factory=SearchTavilyConfig)
    index: SearchIndexProviderConfig = Field(default_factory=SearchIndexProviderConfig)

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
    search: SearchIntegrationConfig = Field(default_factory=SearchIntegrationConfig)
    crawl: SearchCrawlConfig = Field(default_factory=SearchCrawlConfig)

    @model_validator(mode="after")
    def _require_search_db(self) -> SearchSettings:
        if not self.database.search_url:
            raise ValueError("database.search_url is required for search service")
        return self


_search_settings: SearchSettings | None = None


def _apply_crawl_env_overrides(settings: SearchSettings) -> SearchSettings:
    min_extract_chars = os.getenv("CRAWL__MIN_EXTRACT_CHARS")
    if min_extract_chars is None:
        return settings
    return settings.model_copy(
        update={
            "crawl": settings.crawl.model_copy(update={"min_extract_chars": int(min_extract_chars)}),
        }
    )


def get_search_settings() -> SearchSettings:
    global _search_settings
    if _search_settings is None:
        merged = load_merged_config(service_name="search", silent=True)
        _search_settings = _apply_crawl_env_overrides(SearchSettings.model_validate(merged))
    return _search_settings


def reset_search_settings() -> None:
    global _search_settings
    _search_settings = None
