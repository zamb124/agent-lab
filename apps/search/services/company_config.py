"""Resolve effective Search provider config for a company."""

from __future__ import annotations

from dataclasses import dataclass

from apps.search.config import (
    SearchIntegrationConfig,
    SearchLinkupConfig,
    SearchProviderId,
    SearchSerperConfig,
    SearchTavilyConfig,
    SearchTinyFishConfig,
)
from core.ai.company_settings.crypto import decrypt_secret
from core.company_search import (
    CompanyLinkupSearchProvider,
    CompanySearchProviderBase,
    CompanySearchProviders,
    CompanyTavilySearchProvider,
    SearchCredentialSource,
)
from core.models.identity_models import Company


@dataclass(frozen=True, slots=True)
class ResolvedSearchConfig:
    config: SearchIntegrationConfig
    credential_sources: dict[SearchProviderId, SearchCredentialSource]

    def credential_source(self, provider_id: str) -> SearchCredentialSource:
        if provider_id == "tinyfish":
            return self.credential_sources["tinyfish"]
        if provider_id == "linkup":
            return self.credential_sources["linkup"]
        if provider_id == "serper":
            return self.credential_sources["serper"]
        if provider_id == "tavily":
            return self.credential_sources["tavily"]
        return "platform"


def resolve_search_config_for_company(
    *,
    platform_config: SearchIntegrationConfig,
    company: Company | None,
) -> ResolvedSearchConfig:
    if company is None:
        return ResolvedSearchConfig(
            config=platform_config,
            credential_sources={
                "tinyfish": "platform",
                "linkup": "platform",
                "serper": "platform",
                "tavily": "platform",
            },
        )

    company_settings = CompanySearchProviders.from_metadata(company.metadata)
    tinyfish, tinyfish_source = _resolve_tinyfish(platform_config.tinyfish, company_settings.tinyfish)
    linkup, linkup_source = _resolve_linkup(platform_config.linkup, company_settings.linkup)
    serper, serper_source = _resolve_serper(platform_config.serper, company_settings.serper)
    tavily, tavily_source = _resolve_tavily(platform_config.tavily, company_settings.tavily)
    return ResolvedSearchConfig(
        config=platform_config.model_copy(
            update={
                "provider_order": list(company_settings.provider_order),
                "tinyfish": tinyfish,
                "linkup": linkup,
                "serper": serper,
                "tavily": tavily,
            }
        ),
        credential_sources={
            "tinyfish": tinyfish_source,
            "linkup": linkup_source,
            "serper": serper_source,
            "tavily": tavily_source,
        },
    )


def _common_update(
    *,
    platform_api_key: str,
    platform_enabled: bool,
    override: CompanySearchProviderBase,
) -> tuple[dict[str, object], SearchCredentialSource]:
    update: dict[str, object] = {}
    if override.base_url is not None:
        update["base_url"] = override.base_url
    if override.timeout_seconds is not None:
        update["timeout_seconds"] = override.timeout_seconds
    if override.credential_source == "company":
        update["enabled"] = override.enabled
        if override.api_key_encrypted is None:
            raise ValueError("company search provider key is not configured")
        update["api_key"] = decrypt_secret(override.api_key_encrypted)
        return update, "company"
    update["enabled"] = platform_enabled and override.enabled
    update["api_key"] = platform_api_key
    return update, "platform"


def _resolve_tinyfish(
    platform: SearchTinyFishConfig,
    override: CompanySearchProviderBase,
) -> tuple[SearchTinyFishConfig, SearchCredentialSource]:
    update, source = _common_update(
        platform_api_key=platform.api_key,
        platform_enabled=platform.enabled,
        override=override,
    )
    return platform.model_copy(update=update), source


def _resolve_serper(
    platform: SearchSerperConfig,
    override: CompanySearchProviderBase,
) -> tuple[SearchSerperConfig, SearchCredentialSource]:
    update, source = _common_update(
        platform_api_key=platform.api_key,
        platform_enabled=platform.enabled,
        override=override,
    )
    return platform.model_copy(update=update), source


def _resolve_linkup(
    platform: SearchLinkupConfig,
    override: CompanyLinkupSearchProvider,
) -> tuple[SearchLinkupConfig, SearchCredentialSource]:
    update, source = _common_update(
        platform_api_key=platform.api_key,
        platform_enabled=platform.enabled,
        override=override,
    )
    if override.depth is not None:
        update["depth"] = override.depth
    return platform.model_copy(update=update), source


def _resolve_tavily(
    platform: SearchTavilyConfig,
    override: CompanyTavilySearchProvider,
) -> tuple[SearchTavilyConfig, SearchCredentialSource]:
    update, source = _common_update(
        platform_api_key=platform.api_key,
        platform_enabled=platform.enabled,
        override=override,
    )
    if override.search_depth is not None:
        update["search_depth"] = override.search_depth
    if override.topic is not None:
        update["topic"] = override.topic
    if override.include_answer is not None:
        update["include_answer"] = override.include_answer
    return platform.model_copy(update=update), source
