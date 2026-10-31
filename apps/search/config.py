"""Platform index search provider configuration and crawl settings."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.config import BaseSettings
from core.config.loader import get_project_root
from core.config.service_settings import ServiceSettingsCache
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

    provider: str = Field(default="linnex_llm", min_length=1)
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
    max_fetch_attempts: int = Field(default=5, ge=1, le=20)
    fetch_retry_base_seconds: int = Field(default=600, ge=60, le=86400)
    adaptive_refresh_enabled: bool = True
    adaptive_refresh_min_seconds: int = Field(default=3600, ge=60, le=86_400)
    adaptive_refresh_max_seconds: int = Field(default=604_800, ge=3600, le=2_592_000)
    adaptive_refresh_min_samples: int = Field(default=5, ge=1, le=1000)
    adaptive_refresh_lookback_factor: float = Field(default=4.0, ge=1.0, le=20.0)
    politeness_enabled: bool = True
    robots_user_agent: str = Field(default="LinnexBot", min_length=1, max_length=64)
    robots_cache_ttl_seconds: int = Field(default=21_600, ge=300, le=604_800)
    fetch_min_interval_seconds: float = Field(default=1.0, ge=0.0, le=60.0)
    max_crawl_delay_seconds: float = Field(default=30.0, ge=1.0, le=120.0)
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
    serp_cache_key_prefix: str = Field(default="search:serp", min_length=1)
    serp_cache_ttl_seconds: int = Field(default=1800, ge=60, le=7200)
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


_settings_cache = ServiceSettingsCache("search", SearchSettings)
get_search_settings = _settings_cache.get
reset_search_settings = _settings_cache.reset
