"""Pure model validation for LLM fallback model settings."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.flows.src.models.node_config import NodeLLMOverride
from apps.flows.src.models.resource import LLMResourceConfig, LLMResourcePatch


def test_node_llm_override_accepts_and_normalizes_fallback_models() -> None:
    override = NodeLLMOverride(
        model="openrouter:vendor/primary",
        fallback_models=[
            {"model": " vendor/fallback ", "temperature": 0.3},
            {"model": "openai:gpt-4o-mini", "base_url": "https://api.openai.test/v1"},
        ],
    )

    assert override.provider == "openrouter"
    assert override.model == "vendor/primary"
    assert override.fallback_models is not None
    assert override.fallback_models[0].model == "vendor/fallback"
    assert override.fallback_models[0].temperature == 0.3
    assert override.fallback_models[1].provider == "openai"
    assert override.fallback_models[1].model == "gpt-4o-mini"
    assert override.fallback_models[1].base_url == "https://api.openai.test/v1"


def test_node_llm_override_rejects_invalid_fallback_models() -> None:
    with pytest.raises(ValidationError):
        NodeLLMOverride(model="vendor/primary", fallback_models="vendor/fallback")

    with pytest.raises(ValidationError):
        NodeLLMOverride(model="vendor/primary", fallback_models=["vendor/fallback"])

    with pytest.raises(ValidationError):
        NodeLLMOverride(model="vendor/primary", fallback_models=[{}])


def test_llm_resource_config_accepts_fallback_models() -> None:
    config = LLMResourceConfig(
        provider="openrouter",
        model="vendor/primary",
        fallback_models=[
            {"model": "vendor/fallback", "top_p": 0.95},
            {"model": "openai:gpt-4o-mini", "extra_request_headers": {"X-Test": "1"}},
        ],
    )

    assert config.fallback_models is not None
    assert config.fallback_models[0].model == "vendor/fallback"
    assert config.fallback_models[0].top_p == 0.95
    assert config.fallback_models[1].provider == "openai"
    assert config.fallback_models[1].extra_request_headers == {"X-Test": "1"}


def test_llm_resource_patch_accepts_null_or_normalized_fallback_models() -> None:
    assert LLMResourcePatch(fallback_models=None).fallback_models is None
    patch = LLMResourcePatch(fallback_models=[{"model": " vendor/fallback "}])
    assert patch.fallback_models is not None
    assert patch.fallback_models[0].model == "vendor/fallback"


def test_llm_resource_models_reject_invalid_fallback_models() -> None:
    with pytest.raises(ValidationError):
        LLMResourceConfig(
            provider="openrouter",
            model="vendor/primary",
            fallback_models=[{"model": ""}],
        )
    with pytest.raises(ValidationError):
        LLMResourcePatch(fallback_models=[123])


def test_runtime_candidate_metadata_is_not_dumped_into_authoring_config() -> None:
    override = NodeLLMOverride(
        model="vendor/primary",
        fallback_models=[{"model": "vendor/fallback"}],
    )

    dumped = override.model_dump(mode="json", exclude_none=True)

    assert "source" not in dumped
    assert "default_headers" not in dumped
    assert "supported_parameters" not in dumped
    assert "source" not in dumped["fallback_models"][0]
    assert "default_headers" not in dumped["fallback_models"][0]
