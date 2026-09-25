"""
Тесты Registry API.

Реальный сервис, flows загружаются из agents/.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.flows.realtime.registry_operations import (
    _custom_provider_models,
    _custom_provider_options,
    _platform_provider_options,
)
from core.ai.company_settings import CompanyAIProviders, CompanyCustomOpenAICompatibleProvider
from core.ai.free_pool import (
    PlatformFreeModelRecord,
    serialize_platform_free_models,
)
from core.ai.llm_models_service import LLMModelsService
from core.ai.providers import (
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    HUMANITEC_LLMS_DISPLAY_LABEL,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    AICapability,
)
from core.config.models import (
    BothubProviderConfig,
    CailaProviderConfig,
    CerebrasProviderConfig,
    DeepInfraProviderConfig,
    GitHubModelsProviderConfig,
    GoogleLLMProviderConfig,
    GroqProviderConfig,
    HuggingFaceProviderConfig,
    LLMConfig,
    MistralProviderConfig,
    NvidiaProviderConfig,
    OpenAIProviderConfig,
    OpenRouterProviderConfig,
    PlatformFreePoolConfig,
    SambaNovaProviderConfig,
    YandexLLMProviderConfig,
    ZAIProviderConfig,
)


def test_registry_custom_provider_options_use_label_and_custom_ref():
    aip = CompanyAIProviders(
        custom_providers=[
            CompanyCustomOpenAICompatibleProvider(
                id="corp",
                label="Corp LLM",
                base_url="https://llm.example.test/v1",
                api_key_encrypted="encrypted",
                capabilities=["llm_chat"],
                model_by_capability={"llm_chat": "chat-model"},
            )
        ]
    )
    assert [
        item.model_dump(mode="json", exclude_none=True)
        for item in _custom_provider_options(aip, AICapability.LLM_CHAT)
    ] == [{"value": "custom:corp", "label": "Corp LLM", "kind": "custom", "custom_id": "corp"}]
    assert _custom_provider_models(aip, "custom:corp", AICapability.LLM_CHAT) == ["chat-model"]


def test_registry_platform_provider_options_labels_humanitec_llm():
    options = _platform_provider_options(
        ["openrouter", HUMANITEC_LLM_PROVIDER],
        llms_display_label=HUMANITEC_LLMS_DISPLAY_LABEL,
    )
    assert options[0] == "openrouter"
    assert not isinstance(options[1], str)
    assert options[1].model_dump(mode="json", exclude_none=True) == {
        "value": HUMANITEC_LLM_PROVIDER,
        "label": HUMANITEC_LLMS_DISPLAY_LABEL,
        "kind": "virtual",
    }


@pytest.mark.asyncio
async def test_humanitec_llm_models_are_virtual_and_not_read_from_repository():
    redis = AsyncMock()
    redis.get.return_value = serialize_platform_free_models(
        [
            PlatformFreeModelRecord(
                provider="openrouter",
                id="qwen/qwen3-coder:free",
                score=96,
                context_length=262144,
                supported_parameters=("tools", "response_format"),
                input_modalities=("text",),
                output_modalities=("text",),
            )
        ]
    )
    service = LLMModelsService(AsyncMock(), redis)
    assert await service.get_model_ids_by_provider_capability(
        HUMANITEC_LLM_PROVIDER,
        AICapability.LLM_CHAT,
    ) == [
        {
            "value": HUMANITEC_LLM_AUTO_MODEL,
            "label": HUMANITEC_LLM_AUTO_MODEL,
            "kind": "auto",
        },
        {
            "value": "openrouter:qwen/qwen3-coder:free",
            "label": "openrouter / qwen/qwen3-coder:free",
            "kind": "free_model",
            "provider": "openrouter",
            "model_id": "qwen/qwen3-coder:free",
            "score": 96,
            "context_length": 262144,
            "max_tokens": None,
            "supported_parameters": ["tools", "response_format"],
            "input_modalities": ["text"],
            "output_modalities": ["text"],
            "free_reason": "verified_zero_price",
        },
    ]


def test_configured_providers_follow_canonical_provider_order(monkeypatch):
    settings = SimpleNamespace(
        llm=LLMConfig(
            openrouter=OpenRouterProviderConfig(api_key="test-key"),
            bothub=BothubProviderConfig(api_key="test-key"),
            groq=GroqProviderConfig(api_key="test-key"),
            cerebras=CerebrasProviderConfig(api_key="test-key"),
            google=GoogleLLMProviderConfig(api_key="test-key"),
            github=GitHubModelsProviderConfig(api_key="test-key"),
            huggingface=HuggingFaceProviderConfig(api_key="test-key"),
            nvidia=NvidiaProviderConfig(api_key="test-key"),
            mistral=MistralProviderConfig(api_key="test-key"),
            zai=ZAIProviderConfig(api_key="test-key"),
            sambanova=SambaNovaProviderConfig(api_key="test-key"),
            deepinfra=DeepInfraProviderConfig(api_key="test-key"),
            caila=CailaProviderConfig(api_key="test-key"),
            openai=OpenAIProviderConfig(api_key="test-key"),
            yandex=YandexLLMProviderConfig(api_key="test-key", folder_id="folder"),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        )
    )
    monkeypatch.setattr("core.ai.llm_models_service.get_settings", lambda: settings)

    assert LLMModelsService.get_configured_providers() == [
        HUMANITEC_LLM_PROVIDER,
        *OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    ]


def test_humanitec_llm_available_with_account_free_tier_provider(monkeypatch):
    settings = SimpleNamespace(
        llm=LLMConfig(
            groq=GroqProviderConfig(api_key="test-key"),
            platform_free_pool=PlatformFreePoolConfig(enabled=True),
        )
    )
    monkeypatch.setattr("core.ai.llm_models_service.get_settings", lambda: settings)

    assert LLMModelsService.get_configured_providers() == [
        HUMANITEC_LLM_PROVIDER,
        "groq",
    ]


class TestRegistryModels:
    """Тесты /registry/models/values endpoint."""

    @pytest.mark.asyncio
    async def test_get_models_returns_list(self, client):
        """GET /registry/models/values возвращает список моделей."""
        response = await client.get("/flows/api/v1/registry/models/values")
        assert response.status_code == 200
        models = response.json()["items"]
        assert isinstance(models, list)

    @pytest.mark.asyncio
    async def test_models_values_are_strings(self, client):
        """Все элементы списка моделей имеют строковый тип."""
        response = await client.get("/flows/api/v1/registry/models/values")
        models = response.json()["items"]
        assert all((isinstance(model_id, str) for model_id in models))

    @pytest.mark.asyncio
    async def test_unknown_capability_is_400(self, client):
        response = await client.get(
            "/flows/api/v1/registry/models/values",
            params={"capability": "not_a_capability"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_registry_providers_values_linnex_llms_label(client) -> None:
    response = await client.get(
        "/flows/api/v1/registry/providers/values",
        headers={"Host": "linnex.io"},
    )
    assert response.status_code == 200
    items = response.json()["items"]
    humanitec_llm = next(
        item for item in items
        if isinstance(item, dict) and item.get("value") == HUMANITEC_LLM_PROVIDER
    )
    assert humanitec_llm["label"] == "Linnex LLMs"
    assert "Humanitec" not in humanitec_llm["label"]
