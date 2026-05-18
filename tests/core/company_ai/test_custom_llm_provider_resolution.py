from __future__ import annotations

import pytest

from core.company_ai import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    METADATA_KEY,
    AICapability,
    CompanyAIProviders,
    CompanyLLMOverride,
    CompanyCustomOpenAICompatibleProvider,
    resolve_custom_llm_provider_ref,
    resolve_llm_for_capability,
)
from core.context import Company, Context, User, clear_context, set_context
from core.text_transforms.service import TextTransformService


@pytest.fixture(autouse=True)
def _context():
    company = Company(
        company_id="c1",
        name="Company",
        metadata={
            METADATA_KEY: CompanyAIProviders(
                custom_providers=[
                    CompanyCustomOpenAICompatibleProvider(
                        id="corp",
                        label="Corp LLM",
                        base_url="https://llm.example.test/v1",
                        api_key_encrypted="encrypted-token",
                        capabilities=["llm_chat", "llm_summarize", "llm_format_markdown"],
                        model_by_capability={
                            "llm_chat": "chat-model",
                            "llm_summarize": "summary-model",
                            "llm_format_markdown": "markdown-model",
                        },
                        extra_request_headers={"X-Tenant": "c1"},
                        extra_request_body={"metadata": {"tenant": "c1"}},
                    )
                ]
            ).to_metadata_dict()
        },
    )
    user = User(user_id="u1", name="User", active_company_id="c1")
    set_context(Context(user=user, active_company=company, channel="test"))
    try:
        yield
    finally:
        clear_context()


def test_resolve_custom_llm_provider_ref_expands_transport(monkeypatch):
    monkeypatch.setattr("core.company_ai.resolver.decrypt_secret", lambda token: f"plain:{token}")

    resolved = resolve_custom_llm_provider_ref("custom:corp", capability=AICapability.LLM_CHAT)

    assert resolved.provider == "custom_openai_compatible"
    assert resolved.model == "chat-model"
    assert resolved.api_key == "plain:encrypted-token"
    assert resolved.base_url == "https://llm.example.test/v1"
    assert resolved.extra_request_headers == {"X-Tenant": "c1"}
    assert resolved.extra_request_body == {"metadata": {"tenant": "c1"}}
    assert resolved.custom_provider_id == "corp"


def test_resolve_humanitec_llm_company_override_is_platform_virtual_provider():
    company = Company(
        company_id="c2",
        name="Company 2",
        metadata={
            METADATA_KEY: CompanyAIProviders(
                llm_chat=CompanyLLMOverride(provider=HUMANITEC_LLM_PROVIDER)
            ).to_metadata_dict()
        },
    )
    user = User(user_id="u2", name="User 2", active_company_id="c2")
    set_context(Context(user=user, active_company=company, channel="test"))

    resolved = resolve_llm_for_capability(AICapability.LLM_CHAT)

    assert resolved is not None
    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == HUMANITEC_LLM_AUTO_MODEL
    assert resolved.api_key is None
    assert resolved.base_url is None
    assert resolved.cost_origin == "platform"


def test_text_transform_resolves_explicit_custom_provider(monkeypatch):
    monkeypatch.setattr("core.company_ai.resolver.decrypt_secret", lambda token: "plain-key")
    service = TextTransformService()

    provider, model, api_key, base_url, headers, body, cost_origin = service._resolve_company_llm_args(
        AICapability.LLM_SUMMARIZE,
        provider="custom:corp",
        model=None,
    )

    assert provider == "custom_openai_compatible"
    assert model == "summary-model"
    assert api_key == "plain-key"
    assert base_url == "https://llm.example.test/v1"
    assert headers == {"X-Tenant": "c1"}
    assert body == {"metadata": {"tenant": "c1"}}
    assert cost_origin == "company"
