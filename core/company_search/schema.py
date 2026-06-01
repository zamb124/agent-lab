"""Strict schema for per-company Search provider settings."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.types import JsonObject, require_json_object

COMPANY_SEARCH_METADATA_KEY = "search_providers"

SearchProviderId = Literal["tinyfish", "linkup", "serper", "tavily"]
SearchCredentialSource = Literal["platform", "company"]

_PROVIDER_IDS: tuple[SearchProviderId, ...] = ("tinyfish", "linkup", "serper", "tavily")


class CompanySearchProviderBase(BaseModel):
    """Shared provider override fields stored under ``Company.metadata``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    enabled: bool = True
    credential_source: SearchCredentialSource = "platform"
    api_key_encrypted: str | None = None
    base_url: str | None = Field(default=None, min_length=1)
    timeout_seconds: float | None = Field(default=None, ge=1.0, le=60.0)

    @model_validator(mode="after")
    def _credentials_consistent(self) -> "CompanySearchProviderBase":
        if self.credential_source == "company" and not self.api_key_encrypted:
            raise ValueError("api_key_encrypted is required when credential_source='company'")
        if self.credential_source == "platform" and self.api_key_encrypted is not None:
            raise ValueError("api_key_encrypted is only allowed for credential_source='company'")
        return self


class CompanyTinyFishSearchProvider(CompanySearchProviderBase):
    """TinyFish company override."""


class CompanySerperSearchProvider(CompanySearchProviderBase):
    """Serper.dev company override."""


class CompanyLinkupSearchProvider(CompanySearchProviderBase):
    """Linkup company override."""

    depth: Literal["fast", "standard", "deep"] | None = None


class CompanyTavilySearchProvider(CompanySearchProviderBase):
    """Tavily company override."""

    search_depth: Literal["basic", "advanced"] | None = None
    topic: Literal["general", "news", "finance"] | None = None
    include_answer: bool | None = None


class CompanySearchProviders(BaseModel):
    """Root schema for ``Company.metadata['search_providers']``."""

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    provider_order: list[SearchProviderId] = Field(default_factory=lambda: list(_PROVIDER_IDS))
    tinyfish: CompanyTinyFishSearchProvider = Field(default_factory=CompanyTinyFishSearchProvider)
    linkup: CompanyLinkupSearchProvider = Field(default_factory=CompanyLinkupSearchProvider)
    serper: CompanySerperSearchProvider = Field(default_factory=CompanySerperSearchProvider)
    tavily: CompanyTavilySearchProvider = Field(default_factory=CompanyTavilySearchProvider)

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
        for provider_id in _PROVIDER_IDS:
            if provider_id not in seen:
                out.append(provider_id)
        if not out:
            raise ValueError("provider_order must contain at least one provider")
        return out

    @classmethod
    def from_metadata(cls, metadata: JsonObject) -> "CompanySearchProviders":
        raw = metadata.get(COMPANY_SEARCH_METADATA_KEY)
        if raw is None:
            return cls()
        if not isinstance(raw, dict):
            raise ValueError("company.metadata.search_providers must be an object")
        return cls.model_validate(require_json_object(raw, "company.metadata.search_providers"))

    def to_metadata_dict(self) -> JsonObject:
        if self == CompanySearchProviders():
            return {}
        return require_json_object(
            self.model_dump(mode="json", exclude_none=True),
            "CompanySearchProviders",
        )

    def provider(self, provider_id: SearchProviderId) -> CompanySearchProviderBase:
        providers: dict[SearchProviderId, CompanySearchProviderBase] = {
            "tinyfish": self.tinyfish,
            "linkup": self.linkup,
            "serper": self.serper,
            "tavily": self.tavily,
        }
        return providers[provider_id]
