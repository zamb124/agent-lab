"""Unit tests for HumanitecAgent LLM proxy model catalog."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from apps.agent.llm_proxy import (
    _agent_llm_option_value,
    _read_agent_llm_model_ids,
    _resolve_agent_llm_model,
    _validate_requested_agent_model,
)
from core.ai.models import AIModelRecord, ResolvedAIModel
from core.ai.providers import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    AICapability,
)


def test_agent_llm_option_value_reads_string_and_json_object() -> None:
    assert _agent_llm_option_value("auto") == HUMANITEC_LLM_AUTO_MODEL
    assert _agent_llm_option_value({"value": "openrouter:qwen/qwen3-coder:free"}) == (
        "openrouter:qwen/qwen3-coder:free"
    )
    assert _agent_llm_option_value({"label": "auto"}) is None


def test_validate_requested_agent_model_rejects_unknown_model() -> None:
    allowed = {HUMANITEC_LLM_AUTO_MODEL, "openrouter:qwen/qwen3-coder:free"}
    with pytest.raises(HTTPException) as exc_info:
        _validate_requested_agent_model("anthropic:claude-3.5-sonnet", allowed)
    assert exc_info.value.status_code == 400


def test_validate_requested_agent_model_accepts_auto() -> None:
    allowed = {HUMANITEC_LLM_AUTO_MODEL}
    assert _validate_requested_agent_model("auto", allowed) == HUMANITEC_LLM_AUTO_MODEL


@pytest.mark.asyncio
async def test_read_agent_llm_model_ids_uses_catalog_and_llm_models_service() -> None:
    catalog_record = AIModelRecord(
        provider="openrouter",
        model_id="qwen/qwen3-coder:free",
        capabilities=(AICapability.LLM_CHAT,),
        input_modalities=("text",),
        output_modalities=("text",),
    )
    container = MagicMock()
    container.llm_models_service.get_configured_providers_by_capability.return_value = [
        HUMANITEC_LLM_PROVIDER,
        "openrouter",
    ]
    container.ai_model_catalog_repository.list_by_provider_capability = AsyncMock(
        return_value=[catalog_record],
    )
    container.llm_models_service.get_model_ids_by_provider_capability = AsyncMock(
        return_value=[],
    )

    model_ids = await _read_agent_llm_model_ids(container)

    assert model_ids[0] == HUMANITEC_LLM_AUTO_MODEL
    assert "openrouter:qwen/qwen3-coder:free" in model_ids
    container.llm_models_service.get_model_ids_by_provider_capability.assert_not_called()


@pytest.mark.asyncio
async def test_read_agent_llm_model_ids_falls_back_to_humanitec_llm_options() -> None:
    container = MagicMock()
    container.llm_models_service.get_configured_providers_by_capability.return_value = [
        HUMANITEC_LLM_PROVIDER,
    ]
    container.ai_model_catalog_repository.list_by_provider_capability = AsyncMock(
        return_value=[],
    )
    container.llm_models_service.get_model_ids_by_provider_capability = AsyncMock(
        return_value=[
            {"value": HUMANITEC_LLM_AUTO_MODEL, "label": HUMANITEC_LLM_AUTO_MODEL},
            {"value": "groq:llama-3.1-8b-instant", "label": "groq / llama-3.1-8b-instant"},
        ],
    )

    model_ids = await _read_agent_llm_model_ids(container)

    assert model_ids == [HUMANITEC_LLM_AUTO_MODEL, "groq:llama-3.1-8b-instant"]


def test_resolve_agent_llm_model_auto_uses_humanitec_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider=HUMANITEC_LLM_PROVIDER,
        model=HUMANITEC_LLM_AUTO_MODEL,
        cost_origin="platform",
    )

    def fake_resolve_ai_model(
        capability: AICapability,
        selection: object | None = None,
        requirements: object | None = None,
        *,
        include_platform_default: bool = True,
    ) -> ResolvedAIModel | None:
        _ = capability, requirements, include_platform_default
        assert selection is not None
        assert getattr(selection, "provider") == HUMANITEC_LLM_PROVIDER
        assert getattr(selection, "model") == HUMANITEC_LLM_AUTO_MODEL
        return expected

    monkeypatch.setattr("apps.agent.llm_proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_agent_llm_model(HUMANITEC_LLM_AUTO_MODEL)
    assert resolved == expected


def test_resolve_agent_llm_model_provider_prefixed_uses_direct_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = ResolvedAIModel(
        capability=AICapability.LLM_CHAT,
        provider="openrouter",
        model="qwen/qwen3-coder:free",
        cost_origin="platform",
    )

    def fake_resolve_ai_model(
        capability: AICapability,
        selection: object | None = None,
        requirements: object | None = None,
        *,
        include_platform_default: bool = True,
    ) -> ResolvedAIModel | None:
        _ = capability, requirements, include_platform_default
        assert selection is not None
        assert getattr(selection, "provider") == "openrouter"
        assert getattr(selection, "model") == "qwen/qwen3-coder:free"
        return expected

    monkeypatch.setattr("apps.agent.llm_proxy.resolve_ai_model", fake_resolve_ai_model)
    resolved = _resolve_agent_llm_model("openrouter:qwen/qwen3-coder:free")
    assert resolved == expected
