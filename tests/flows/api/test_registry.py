"""
Тесты Registry API.

Реальный сервис, flows загружаются из agents/.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from apps.flows.src.api.registry import (
    _custom_provider_models,
    _custom_provider_options,
    _platform_provider_options,
)
from apps.flows.src.services.llm_models_service import LLMModelsService
from core.clients.llm.model_routing import (
    ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS,
    HUMANITEC_LLM_AUTO_MODEL,
    HUMANITEC_LLM_PROVIDER,
    HUMANITEC_LLMS_DISPLAY_LABEL,
    OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
)
from core.clients.llm.platform_free_models import (
    PlatformFreeModelRecord,
    serialize_platform_free_models,
)
from core.company_ai import CompanyAIProviders, CompanyCustomOpenAICompatibleProvider


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
        item.model_dump(mode="json", exclude_none=True) for item in _custom_provider_options(aip)
    ] == [{"value": "custom:corp", "label": "Corp LLM", "kind": "custom", "custom_id": "corp"}]
    assert _custom_provider_models(aip, "custom:corp") == ["chat-model"]


def test_registry_platform_provider_options_labels_humanitec_llm():
    options = _platform_provider_options(["openrouter", HUMANITEC_LLM_PROVIDER])
    assert options[0] == "openrouter"
    assert not isinstance(options[1], str)
    assert options[1].model_dump(mode="json", exclude_none=True) == {
        "value": HUMANITEC_LLM_PROVIDER,
        "label": HUMANITEC_LLMS_DISPLAY_LABEL,
        "kind": "virtual",
    }


@pytest.mark.asyncio
async def test_humanitec_llm_models_are_virtual_and_not_read_from_repository():
    class Repo:
        async def list_by_provider(self, provider):
            raise AssertionError(f"unexpected repository call for {provider}")

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
    service = LLMModelsService(Repo(), AsyncMock(), redis)  # pyright: ignore[reportArgumentType]
    assert await service.get_models_by_provider(HUMANITEC_LLM_PROVIDER) == [
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
    provider_configs = {
        provider: SimpleNamespace(api_key="test-key")
        for provider in OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER
    }
    for provider in ACCOUNT_FREE_TIER_LLM_PROVIDER_SLUGS:
        provider_configs[provider] = SimpleNamespace(
            api_key="test-key",
            smoke_model=f"{provider}/smoke",
        )
    provider_configs["yandex"] = SimpleNamespace(api_key="test-key", folder_id="folder")
    settings = SimpleNamespace(
        llm=SimpleNamespace(
            **provider_configs,
            platform_free_pool=SimpleNamespace(
                enabled=True,
                providers=OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
            ),
        )
    )
    monkeypatch.setattr("apps.flows.src.services.llm_models_service.get_settings", lambda: settings)

    assert LLMModelsService.get_configured_providers() == [
        HUMANITEC_LLM_PROVIDER,
        *OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
    ]


def test_humanitec_llm_available_with_account_free_tier_provider(monkeypatch):
    settings = SimpleNamespace(
        llm=SimpleNamespace(
            openrouter=None,
            bothub=None,
            groq=SimpleNamespace(api_key="test-key", smoke_model="llama-3.1-8b-instant"),
            google=None,
            github=None,
            huggingface=None,
            deepinfra=None,
            openai=None,
            yandex=None,
            platform_free_pool=SimpleNamespace(
                enabled=True,
                providers=OPENAI_COMPATIBLE_LLM_PROVIDER_ORDER,
            ),
        )
    )
    monkeypatch.setattr("apps.flows.src.services.llm_models_service.get_settings", lambda: settings)

    assert LLMModelsService.get_configured_providers() == [
        HUMANITEC_LLM_PROVIDER,
        "groq",
    ]


class TestRegistryAgents:
    """Тесты /registry/flows endpoint."""

    @pytest.mark.asyncio
    async def test_get_agents_returns_list(self, client):
        """GET /registry/flows возвращает список flows как AgentCard[]."""
        response = await client.get("/flows/api/v1/registry/flows")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_agent_card_has_required_fields(self, client):
        """AgentCard содержит обязательные поля."""
        response = await client.get("/flows/api/v1/registry/flows")
        agents = response.json()
        if len(agents) > 0:
            agent = agents[0]
            assert "name" in agent
            assert "url" in agent
            assert "branches" in agent
            assert "version" in agent
            assert "protocolVersion" in agent

    @pytest.mark.asyncio
    async def test_agent_card_has_branches(self, client):
        """AgentCard содержит как минимум одну ветку (branch)."""
        response = await client.get("/flows/api/v1/registry/flows")
        agents = response.json()
        if len(agents) > 0:
            agent = agents[0]
            branches = agent.get("branches", [])
            assert len(branches) >= 1
            assert "id" in branches[0]
            assert "name" in branches[0]

    @pytest.mark.asyncio
    async def test_agent_url_is_absolute(self, client):
        """URL в AgentCard абсолютный."""
        response = await client.get("/flows/api/v1/registry/flows")
        agents = response.json()
        if len(agents) > 0:
            url = agents[0].get("url", "")
            assert url.startswith("http")


class TestRegistryTools:
    """Тесты /registry/tools endpoint."""

    @pytest.mark.asyncio
    async def test_get_tools_returns_list(self, client):
        """GET /registry/tools возвращает список."""
        response = await client.get("/flows/api/v1/registry/tools")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_tools_have_required_fields(self, client):
        """Tools содержат обязательные поля для platformweb."""
        response = await client.get("/flows/api/v1/registry/tools")
        tools = response.json()
        assert len(tools) > 0
        tool = tools[0]
        assert "name" in tool
        assert "type" in tool
        assert "attributes" in tool
        assert "description" in tool["attributes"]
        assert "parameters_schema" in tool["attributes"]

    @pytest.mark.asyncio
    async def test_calculator_tool_has_parameters(self, client, app):
        """Calculator tool имеет параметры."""
        response = await client.get("/flows/api/v1/registry/tools")
        tools = response.json()
        calculator = next((t for t in tools if t["name"] == "calculator"), None)
        assert calculator is not None, (
            f"Calculator not found in tools: {[t['name'] for t in tools]}"
        )
        parameters_schema = calculator["attributes"]["parameters_schema"]
        assert parameters_schema["properties"].get("expression") is not None, (
            f"Expression not found in parameters_schema: {parameters_schema}"
        )


class TestRegistryModels:
    """Тесты /registry/models/values endpoint."""

    @pytest.mark.asyncio
    async def test_get_models_returns_list(self, client):
        """GET /registry/models/values возвращает список моделей."""
        response = await client.get("/flows/api/v1/registry/models/values")
        assert response.status_code == 200
        models = response.json()
        assert isinstance(models, list)

    @pytest.mark.asyncio
    async def test_models_values_are_strings(self, client):
        """Все элементы списка моделей имеют строковый тип."""
        response = await client.get("/flows/api/v1/registry/models/values")
        models = response.json()
        assert all((isinstance(model_id, str) for model_id in models))


class TestFlowSchema:
    """Тесты /registry/flows/{flow_id}/schema endpoint."""

    @pytest.mark.asyncio
    async def test_schema_returns_html(self, client):
        """GET /registry/flows/{flow_id}/schema возвращает HTML."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    @pytest.mark.asyncio
    async def test_schema_contains_flow_title(self, client):
        """HTML содержит название flow."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "Пример графового flow" in html

    @pytest.mark.asyncio
    async def test_schema_contains_mermaid(self, client):
        """HTML содержит Mermaid диаграмму."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert 'class="mermaid"' in html
        assert "flowchart TD" in html

    @pytest.mark.asyncio
    async def test_schema_contains_skills_tabs(self, client):
        """HTML содержит табы для skills."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "fast_track" in html
        assert "orders_only" in html

    @pytest.mark.asyncio
    async def test_schema_contains_nodes(self, client):
        """HTML содержит ноды flow."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "classifier" in html
        assert "formatter" in html
        assert "Агент" in html or "react" in html.lower()

    @pytest.mark.asyncio
    async def test_schema_contains_edges_conditions(self, client):
        """HTML содержит условия переходов."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "route" in html
        assert "order" in html

    @pytest.mark.asyncio
    async def test_schema_404_for_unknown_flow(self, client):
        """404 для несуществующего flow."""
        response = await client.get("/flows/api/v1/registry/flows/nonexistent_flow/schema")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_schema_contains_legend(self, client):
        """HTML содержит легенду компонентов."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "Components" in html
        assert "React node" in html
        assert "Function" in html

    @pytest.mark.asyncio
    async def test_llm_node_schema_has_tools(self, client):
        """Схема react-ноды содержит tools."""
        response = await client.get("/flows/api/v1/registry/flows/example_react/schema")
        html = response.text
        assert "calculator" in html or "ask_user" in html

    @pytest.mark.asyncio
    async def test_llm_node_schema_has_nested_flows(self, client):
        """Схема react-ноды содержит вложенный flow (как tool)."""
        response = await client.get("/flows/api/v1/registry/flows/example_react/schema")
        html = response.text
        assert "subflow" in html.lower() or "example_subflow" in html or "Субагент" in html

    @pytest.mark.asyncio
    async def test_schema_has_dark_theme(self, client):
        """HTML использует темную тему."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "#0f0f23" in html or "linear-gradient" in html

    @pytest.mark.asyncio
    async def test_schema_entry_point_shown(self, client):
        """HTML показывает entry point."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "Entry:" in html
        assert "classifier" in html

    @pytest.mark.asyncio
    async def test_schema_skill_description_shown(self, client):
        """HTML показывает описание skill."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "Пропускает форматирование" in html or "сразу к ответу" in html.lower()

    @pytest.mark.asyncio
    async def test_schema_mermaid_has_start_end(self, client):
        """Mermaid диаграмма имеет start и END ноды."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text
        assert "start" in html
        assert "END" in html

    @pytest.mark.asyncio
    async def test_schema_nodes_show_display_names(self, client):
        """Ноды показываются с человекочитаемым именем из конфига."""
        response = await client.get("/flows/api/v1/registry/flows/example_react/schema")
        html = response.text
        assert "Главный" in html or "главн" in html.lower()
