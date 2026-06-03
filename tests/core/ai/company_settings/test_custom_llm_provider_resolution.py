from __future__ import annotations

import pytest

from core.ai.company_settings import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    METADATA_KEY,
    CompanyAIProviders,
    CompanyCustomOpenAICompatibleProvider,
    CompanyLLMOverride,
)
from core.ai.providers import AICapability
from core.ai.requirements import AISelection
from core.ai.resolver import resolve_ai_model
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
    monkeypatch.setattr("core.ai.company_settings.resolver.decrypt_secret", lambda token: f"plain:{token}")

    resolved = resolve_ai_model(
        AICapability.LLM_CHAT,
        selection=AISelection(provider="custom:corp", model=None),
        include_platform_default=False,
    )

    assert resolved is not None
    assert resolved.provider == "custom_openai_compatible"
    assert resolved.model == "chat-model"
    assert resolved.api_key == "plain:encrypted-token"
    assert resolved.base_url == "https://llm.example.test/v1"
    assert resolved.headers == {"X-Tenant": "c1"}
    assert resolved.body == {"metadata": {"tenant": "c1"}}
    assert resolved.metadata["custom_provider_id"] == "corp"


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

    resolved = resolve_ai_model(AICapability.LLM_CHAT, include_platform_default=False)

    assert resolved is not None
    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == HUMANITEC_LLM_AUTO_MODEL
    assert resolved.api_key is None
    assert resolved.base_url is None
    assert resolved.cost_origin == "platform"


def test_resolve_humanitec_llms_concrete_free_model_and_fallback_policy():
    company = Company(
        company_id="c2",
        name="Company 2",
        metadata={
            METADATA_KEY: CompanyAIProviders(
                llm_chat=CompanyLLMOverride(
                    provider=HUMANITEC_LLM_PROVIDER,
                    model="openrouter:qwen/qwen3-coder:free",
                    fallback_models=[
                        {"provider": HUMANITEC_LLM_PROVIDER, "model": HUMANITEC_LLM_AUTO_MODEL},
                    ],
                )
            ).to_metadata_dict()
        },
    )
    user = User(user_id="u2", name="User 2", active_company_id="c2")
    set_context(Context(user=user, active_company=company, channel="test"))

    resolved = resolve_ai_model(AICapability.LLM_CHAT, include_platform_default=False)

    assert resolved is not None
    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == "openrouter:qwen/qwen3-coder:free"
    assert resolved.fallback_models[0]["provider"] == HUMANITEC_LLM_PROVIDER
    assert resolved.fallback_models[0]["model"] == HUMANITEC_LLM_AUTO_MODEL


def test_resolve_llm_platform_default_is_humanitec_auto():
    resolved = resolve_ai_model(
        AICapability.LLM_VISION,
        include_platform_default=True,
    )

    assert resolved is not None
    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == HUMANITEC_LLM_AUTO_MODEL
    assert resolved.cost_origin == "platform"


def test_humanitec_llm_company_override_supports_vision_capability():
    company = Company(
        company_id="c3",
        name="Company 3",
        metadata={
            METADATA_KEY: CompanyAIProviders(
                llm_vision=CompanyLLMOverride(provider=HUMANITEC_LLM_PROVIDER)
            ).to_metadata_dict()
        },
    )
    user = User(user_id="u3", name="User 3", active_company_id="c3")
    set_context(Context(user=user, active_company=company, channel="test"))

    resolved = resolve_ai_model(AICapability.LLM_VISION, include_platform_default=False)

    assert resolved is not None
    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == HUMANITEC_LLM_AUTO_MODEL


def test_text_transform_resolves_explicit_custom_provider(monkeypatch):
    monkeypatch.setattr("core.ai.company_settings.resolver.decrypt_secret", lambda token: "plain-key")
    service = TextTransformService()

    resolved = service._resolve_company_llm_args(
        AICapability.LLM_SUMMARIZE,
        provider="custom:corp",
        model=None,
    )

    assert resolved.provider == "custom_openai_compatible"
    assert resolved.model == "summary-model"
    assert resolved.api_key == "plain-key"
    assert resolved.base_url == "https://llm.example.test/v1"
    assert resolved.headers == {"X-Tenant": "c1"}
    assert resolved.body == {"metadata": {"tenant": "c1"}}
    assert resolved.fallback_models == ()
    assert resolved.cost_origin == "company"


def test_text_transform_uses_humanitec_default_without_company_override():
    service = TextTransformService()

    resolved = service._resolve_company_llm_args(
        AICapability.LLM_SUMMARIZE,
        provider=None,
        model=None,
    )

    assert resolved.provider == HUMANITEC_LLM_PROVIDER
    assert resolved.model == HUMANITEC_LLM_AUTO_MODEL
    assert resolved.api_key is None
    assert resolved.base_url is None
    assert resolved.headers == {}
    assert resolved.body == {}
    assert resolved.fallback_models == ()
    assert resolved.cost_origin == "platform"
