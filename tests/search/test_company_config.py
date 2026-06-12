from __future__ import annotations

from apps.search.config import SearchIntegrationConfig
from apps.search.services.company_config import resolve_search_config_for_company
from core.ai.company_settings import encrypt_secret
from core.company_search import COMPANY_SEARCH_METADATA_KEY, CompanySearchProviders
from core.models.identity_models import Company


def test_resolve_search_config_uses_company_credentials_without_touching_platform_config() -> None:
    platform = SearchIntegrationConfig.model_validate(
        {
            "provider_order": ["tinyfish", "linkup", "serper", "tavily"],
            "tinyfish": {"api_key": "platform-tinyfish", "enabled": False},
            "linkup": {"api_key": "platform-linkup", "enabled": True},
            "serper": {"api_key": "platform-serper", "enabled": True},
            "tavily": {"api_key": "platform-tavily", "enabled": True},
        }
    )
    company_settings = CompanySearchProviders.model_validate(
        {
            "provider_order": ["tavily", "serper"],
            "tavily": {
                "credential_source": "company",
                "api_key_encrypted": encrypt_secret("company-tavily-key"),
                "search_depth": "advanced",
                "topic": "news",
                "include_answer": True,
                "timeout_seconds": 20,
            },
            "serper": {
                "enabled": False,
                "credential_source": "platform",
            },
        }
    )
    company = Company(
        company_id="search_company",
        name="Search Company",
        metadata={COMPANY_SEARCH_METADATA_KEY: company_settings.to_metadata_dict()},
    )

    resolved = resolve_search_config_for_company(platform_config=platform, company=company)

    assert resolved.config.provider_order == ["index", "tavily", "serper", "tinyfish", "linkup"]
    assert resolved.credential_source("tavily") == "company"
    assert resolved.config.tavily.api_key == "company-tavily-key"
    assert resolved.config.tavily.search_depth == "advanced"
    assert resolved.config.tavily.topic == "news"
    assert resolved.config.tavily.include_answer is True
    assert resolved.config.tavily.timeout_seconds == 20
    assert resolved.credential_source("serper") == "platform"
    assert resolved.config.serper.api_key == "platform-serper"
    assert resolved.config.serper.enabled is False
    assert resolved.credential_source("tinyfish") == "platform"
    assert resolved.config.tinyfish.enabled is False
    assert platform.tavily.api_key == "platform-tavily"
