from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import NodeConfig, NodeLLMConfig, NodeType
from apps.flows.src.runtime.effective_llm_config import resolve_effective_llm_config_for_node
from core.company_ai import (
    HUMANITEC_LLM_PROVIDER,
    METADATA_KEY,
    CompanyAIProviders,
    CompanyLLMOverride,
)
from core.context import Company, Context, User, clear_context, set_context


@pytest.fixture(autouse=True)
def _clear_context():
    clear_context()
    try:
        yield
    finally:
        clear_context()


def _set_company(metadata: dict | None = None) -> None:
    company = Company(company_id="c1", name="Company", metadata=metadata or {})
    user = User(user_id="u1", name="User", active_company_id="c1")
    set_context(Context(user=user, active_company=company, channel="test"))


def _node(llm: NodeLLMConfig, *, capability: str | None = None) -> NodeConfig:
    return NodeConfig(
        node_id="main",
        type=NodeType.LLM_NODE,
        name="Main",
        description="",
        llm=llm,
        llm_capability=capability,
    )


def test_company_capability_override_wins_over_flow_primary_and_fallbacks() -> None:
    _set_company(
        {
            METADATA_KEY: CompanyAIProviders(
                llm_chat=CompanyLLMOverride(
                    provider="openrouter",
                    model="company/primary",
                    fallback_models=[
                        {"provider": "openrouter", "model": "company/fallback"},
                    ],
                )
            ).to_metadata_dict()
        }
    )
    node = _node(
        NodeLLMConfig(
            provider=HUMANITEC_LLM_PROVIDER,
            model="auto",
            temperature=0.4,
        )
    )

    effective = resolve_effective_llm_config_for_node(node)

    assert effective.source == "company_capability"
    assert effective.config.provider == "openrouter"
    assert effective.config.model == "company/primary"
    assert effective.config.temperature == 0.4
    assert effective.config.fallback_models is not None
    assert effective.config.fallback_models[0].model == "company/fallback"


def test_flow_node_fallback_models_are_rejected_without_company_policy() -> None:
    _set_company()
    node = _node(
        NodeLLMConfig(
            provider="openrouter",
            model="flow/primary",
            fallback_models=[{"provider": "openrouter", "model": "flow/fallback"}],
        )
    )

    with pytest.raises(ValueError, match="fallback policy"):
        resolve_effective_llm_config_for_node(node)


def test_missing_company_override_requires_explicit_provider_and_model() -> None:
    _set_company()
    node = _node(NodeLLMConfig(model="flow/model"))

    with pytest.raises(ValueError, match="settings.llm.default_model"):
        resolve_effective_llm_config_for_node(node)


def test_humanitec_company_override_rejects_configured_fallback_policy() -> None:
    with pytest.raises(ValidationError, match="humanitec_llm"):
        CompanyLLMOverride(
            provider=HUMANITEC_LLM_PROVIDER,
            fallback_models=[{"provider": "openrouter", "model": "fallback"}],
        )


def test_byok_company_primary_rejects_platform_cost_fallback() -> None:
    _set_company(
        {
            METADATA_KEY: CompanyAIProviders(
                llm_chat=CompanyLLMOverride(
                    provider="openrouter",
                    model="company/primary",
                    base_url="https://openrouter.ai/api/v1",
                    fallback_models=[
                        {"provider": "openrouter", "model": "platform/fallback"},
                    ],
                )
            ).to_metadata_dict()
        }
    )
    node = _node(NodeLLMConfig(provider=HUMANITEC_LLM_PROVIDER, model="auto"))

    with pytest.raises(ValueError, match="смешивает"):
        resolve_effective_llm_config_for_node(node)
