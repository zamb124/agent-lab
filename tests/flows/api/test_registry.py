"""
Тесты Registry API.

Реальный сервис, flows загружаются из agents/.
"""

import pytest


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

            # Обязательные поля A2A протокола
            assert "name" in agent
            assert "url" in agent
            assert "skills" in agent
            assert "version" in agent
            assert "protocolVersion" in agent

    @pytest.mark.asyncio
    async def test_agent_card_has_skills(self, client):
        """AgentCard содержит как минимум один skill."""
        response = await client.get("/flows/api/v1/registry/flows")
        agents = response.json()

        if len(agents) > 0:
            agent = agents[0]
            skills = agent.get("skills", [])

            assert len(skills) >= 1
            # У каждого skill есть id и name
            assert "id" in skills[0]
            assert "name" in skills[0]

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

        # Должны быть загружены tools из модулей
        assert len(tools) > 0

        tool = tools[0]
        # Структура для platformweb
        assert "name" in tool
        assert "type" in tool
        assert "attributes" in tool
        assert "description" in tool["attributes"]
        assert "args_schema" in tool["attributes"]

    @pytest.mark.asyncio
    async def test_calculator_tool_has_parameters(self, client, app):
        """Calculator tool имеет параметры."""
        response = await client.get("/flows/api/v1/registry/tools")
        tools = response.json()

        calculator = next((t for t in tools if t["name"] == "calculator"), None)
        assert calculator is not None, f"Calculator not found in tools: {[t['name'] for t in tools]}"
        args_schema = calculator["attributes"]["args_schema"]
        assert args_schema.get("expression") is not None, f"Expression not found in args_schema: {args_schema}"


class TestRegistryModels:
    """Тесты /registry/models/values endpoint."""

    @pytest.mark.asyncio
    async def test_get_models_returns_list(self, client):
        """GET /registry/models/values возвращает список моделей."""
        response = await client.get("/flows/api/v1/registry/models/values")

        assert response.status_code == 200
        models = response.json()
        assert isinstance(models, list)
        assert len(models) > 0

    @pytest.mark.asyncio
    async def test_models_contain_gpt4(self, client):
        """Список моделей содержит модель семейства GPT-4."""
        response = await client.get("/flows/api/v1/registry/models/values")
        models = response.json()

        assert any("gpt-4" in m for m in models), f"Нет модели gpt-4 в списке: {models[:10]}..."


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

        assert "class=\"mermaid\"" in html
        assert "flowchart TD" in html

    @pytest.mark.asyncio
    async def test_schema_contains_skills_tabs(self, client):
        """HTML содержит табы для skills."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text

        # example_graph имеет skills: fast_track, orders_only
        assert "fast_track" in html
        assert "orders_only" in html

    @pytest.mark.asyncio
    async def test_schema_contains_nodes(self, client):
        """HTML содержит ноды flow."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text

        # example_graph имеет ноды: classifier, order/complaint/general процессоры, formatter
        # classifier и formatter это function ноды - показываются по node_id
        assert "classifier" in html
        assert "formatter" in html
        # Процессоры — llm_node, в данных примера в имени может быть «Агент»
        assert "Агент" in html or "react" in html.lower()

    @pytest.mark.asyncio
    async def test_schema_contains_edges_conditions(self, client):
        """HTML содержит условия переходов."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text

        # example_graph имеет условия route = 'order', route = 'complaint'
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

        # example_react main агент имеет tools: calculator, ask_user
        # Проверяем что хотя бы один tool есть
        assert "calculator" in html or "ask_user" in html

    @pytest.mark.asyncio
    async def test_llm_node_schema_has_nested_flows(self, client):
        """Схема react-ноды содержит вложенный flow (как tool)."""
        response = await client.get("/flows/api/v1/registry/flows/example_react/schema")
        html = response.text

        assert (
            "subflow" in html.lower()
            or "example_subflow" in html
            or "Субагент" in html
        )

    @pytest.mark.asyncio
    async def test_schema_has_dark_theme(self, client):
        """HTML использует темную тему."""
        response = await client.get("/flows/api/v1/registry/flows/example_graph/schema")
        html = response.text

        # Проверяем темный фон
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

        # Проверяем что описание skill отображается
        # fast_track skill: "Пропускает форматирование, сразу к ответу"
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

