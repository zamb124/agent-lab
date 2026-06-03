from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.ai.providers import (
    AICapability,
    platform_provider_specs_for_capability,
    provider_supports_capability,
)
from core.company_ai import CompanyAIProviders


def test_embedding_catalog_is_provider_capability_registry_not_model_source() -> None:
    providers = {
        spec.provider
        for spec in platform_provider_specs_for_capability(AICapability.EMBEDDING)
    }
    assert "openrouter" in providers
    assert "bothub" in providers
    assert "huggingface" in providers
    assert "deepinfra" in providers
    assert "provider_litserve" in providers
    assert "groq" not in providers
    assert "github" not in providers


def test_provider_litserve_is_embedding_and_rerank_provider_not_llm() -> None:
    assert provider_supports_capability("provider_litserve", AICapability.EMBEDDING)
    assert provider_supports_capability("provider_litserve", AICapability.RERANK)
    assert not provider_supports_capability("provider_litserve", AICapability.LLM_CHAT)


def test_openrouter_is_rerank_provider() -> None:
    providers = {
        spec.provider
        for spec in platform_provider_specs_for_capability(AICapability.RERANK)
    }
    assert "openrouter" in providers
    assert "provider_litserve" in providers


def test_company_embedding_override_requires_explicit_model_and_dimension() -> None:
    with pytest.raises(ValidationError):
        _ = CompanyAIProviders.model_validate({"embedding": {"provider": "openrouter"}})

    aip = CompanyAIProviders.model_validate(
        {
            "embedding": {
                "provider": "provider_litserve",
                "model": "qwen/qwen3-embedding-0.6b",
                "dimension": 1024,
            }
        },
    )

    assert aip.embedding is not None
    assert aip.embedding.provider == "provider_litserve"
    assert aip.embedding.model == "qwen/qwen3-embedding-0.6b"
    assert aip.embedding.dimension == 1024


def test_company_rerank_override_requires_model_for_enabled_provider() -> None:
    with pytest.raises(ValidationError):
        _ = CompanyAIProviders.model_validate({"rerank": {"provider": "openrouter"}})

    aip = CompanyAIProviders.model_validate(
        {
            "rerank": {
                "provider": "openrouter",
                "model": "openrouter/rerank-test",
            }
        },
    )

    assert aip.rerank is not None
    assert aip.rerank.provider == "openrouter"
    assert aip.rerank.model == "openrouter/rerank-test"
