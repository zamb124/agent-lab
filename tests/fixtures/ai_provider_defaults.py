"""Тестовые дефолты AI-провайдеров компании.

В production runtime — fail-closed: LLM-ноды требуют явный provider/model
или company capability override. Тесты общего исполнения flow используют
этот helper, чтобы override компании был явным в контексте теста и в
компаниях, сохранённых в репозиториях.
"""

from __future__ import annotations

from typing import Any

from core.ai.company_settings import (
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
    """Возвращает AI-провайдеров компании с заполненными text LLM override для тестов."""
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
    """Добавляет тестовые text LLM override в словарь Company.metadata."""
    metadata = dict(existing_metadata or {})
    metadata[METADATA_KEY] = build_test_ai_providers(metadata).to_metadata_dict()
    return metadata


def company_with_test_ai_provider_defaults(company: Company) -> Company:
    """Возвращает копию компании с явными тестовыми text LLM capability override."""
    metadata = build_test_ai_providers_metadata(company.metadata)
    return company.model_copy(update={"metadata": metadata})


def make_test_company(
    *,
    company_id: str = "system",
    name: str = "System",
    **kwargs: Any,
) -> Company:
    """Создаёт тестовую Company с явными text LLM capability override."""
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
