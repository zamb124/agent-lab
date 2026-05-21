"""Test-only company AI provider defaults.

Production runtime stays fail-closed: LLM nodes require either explicit
provider/model or a company capability override. Tests that exercise generic
flow execution use this helper to make the company override explicit in the
test context and in test companies persisted to repositories.
"""

from __future__ import annotations

from typing import Any

from core.company_ai import (
    METADATA_KEY,
    CompanyAIProviders,
    CompanyLLMOverride,
)
from core.models.identity_models import Company

TEST_LLM_PROVIDER = "openrouter"
TEST_LLM_MODEL = "mock-gpt-4"

_TEXT_LLM_CAPABILITY_FIELDS = (
    "llm_chat",
    "llm_summarize",
    "llm_format_markdown",
    "llm_codegen",
)


def build_test_ai_providers(
    existing_metadata: dict[str, Any] | None = None,
) -> CompanyAIProviders:
    """Return company AI providers with missing text LLM overrides filled for tests."""
    metadata = dict(existing_metadata or {})
    providers = CompanyAIProviders.from_metadata(metadata)

    updates: dict[str, CompanyLLMOverride] = {}
    for capability_field in _TEXT_LLM_CAPABILITY_FIELDS:
        if getattr(providers, capability_field) is None:
            updates[capability_field] = CompanyLLMOverride(
                provider=TEST_LLM_PROVIDER,
                model=TEST_LLM_MODEL,
            )

    if not updates:
        return providers
    return providers.model_copy(update=updates)


def build_test_ai_providers_metadata(
    existing_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge test text LLM overrides into a Company.metadata dict."""
    metadata = dict(existing_metadata or {})
    metadata[METADATA_KEY] = build_test_ai_providers(metadata).to_metadata_dict()
    return metadata


def company_with_test_ai_provider_defaults(company: Company) -> Company:
    """Return a copy of company with explicit test text LLM capability overrides."""
    metadata = build_test_ai_providers_metadata(company.metadata)
    return company.model_copy(update={"metadata": metadata})


def make_test_company(
    *,
    company_id: str = "system",
    name: str = "System",
    **kwargs: Any,
) -> Company:
    """Build a test Company with explicit text LLM capability overrides."""
    company = Company(company_id=company_id, name=name, **kwargs)
    return company_with_test_ai_provider_defaults(company)


__all__ = [
    "TEST_LLM_MODEL",
    "TEST_LLM_PROVIDER",
    "build_test_ai_providers",
    "build_test_ai_providers_metadata",
    "company_with_test_ai_provider_defaults",
    "make_test_company",
]
