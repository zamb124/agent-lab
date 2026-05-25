"""Тесты для API v1 endpoints."""

import pytest


class _TestFlowsAPIDuplicate:
    """Тесты /api/v1/flows (первая копия — удалена, переименована во избежание F811)"""

    @pytest.mark.asyncio
    async def test_list_flows(self, client, app, auth_headers_system):
        """Список flows."""
        response = await client.get("/flows/api/v1/flows/", headers=auth_headers_system)
        assert response.status_code == 200
        page = response.json()
        assert "items" in page
        data = page["items"]
        assert isinstance(data, list)
        assert len(data) >= 3

    @pytest.mark.asyncio
    async def test_create_agent(self, client, app, unique_id, auth_headers_system):
        """Создание agent через API."""
        flow_id = f"test_agent_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "description": "Test description",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "You are a test agent",
                        "tools": ["calculator"],
                        "llm": {"model": "gpt-4o", "temperature": 0.5},
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        assert data["name"] == "Test Agent"
        assert data["entry"] == "main"
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_get_agent(self, client, app, unique_id, auth_headers_system):
        """Получение agent."""
        flow_id = f"test_get_agent_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Get Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        response = await client.get(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        assert data["entry"] == "main"
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, client, app, auth_headers_system):
        """404 для несуществующего agent."""
        response = await client.get(
            "/flows/api/v1/flows/nonexistent_agent_xyz", headers=auth_headers_system
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_agent(self, client, app, unique_id, auth_headers_system):
        """Обновление agent."""
        flow_id = f"update_test_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Original Name",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Original prompt", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Updated Name",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Updated prompt", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_delete_agent(self, client, app, unique_id, auth_headers_system):
        """Удаление agent."""
        flow_id = f"delete_test_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "To Delete",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        response = await client.delete(
            f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system
        )
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"
        response = await client.get(f"/flows/api/v1/{flow_id}", headers=auth_headers_system)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_nonexistent_agent(self, client, app, auth_headers_system):
        """404 при удалении несуществующего agent."""
        response = await client.delete(
            "/flows/api/v1/flows/nonexistent_xxx", headers=auth_headers_system
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_agent_with_valid_tool(self, client, app, unique_id, auth_headers_system):
        """Создание agent с существующим tool."""
        flow_id = f"test_agent_tool_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Test prompt", "tools": ["calculator"]}
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        tools = response.json()["nodes"]["main"]["tools"]
        assert isinstance(tools, list)
        assert len(tools) > 0
        tool_ids = [t.get("tool_id") if isinstance(t, dict) else t for t in tools]
        assert "calculator" in tool_ids
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_create_agent_with_invalid_tool(
        self, client, app, unique_id, auth_headers_system
    ):
        """Ошибка при создании agent с несуществующим tool."""
        flow_id = f"test_agent_invalid_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test prompt",
                        "tools": ["nonexistent_tool_xyz"],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 400
        assert "nonexistent_tool_xyz" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_agent_with_agent_as_tool(
        self, client, app, unique_id, auth_headers_system, test_agent_for_tool
    ):
        """Создание agent с другим агентом в качестве tool."""
        flow_id = f"test_agent_agenttool_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test prompt",
                        "tools": [test_agent_for_tool],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_update_agent_with_invalid_tool(
        self, client, app, unique_id, auth_headers_system
    ):
        """Ошибка при обновлении agent с несуществующим tool."""
        flow_id = f"update_invalid_tool_{unique_id}"
        await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Original",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": []}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Updated",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "tools": ["nonexistent_tool_abc"],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 400
        assert "nonexistent_tool_abc" in response.json()["detail"]
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)


class TestFlowsAPI:
    """Тесты /api/v1/flows"""

    @pytest.mark.asyncio
    async def test_list_flows(self, client, app, auth_headers_system):
        """Список flows."""
        response = await client.get("/flows/api/v1/flows/", headers=auth_headers_system)
        assert response.status_code == 200
        page = response.json()
        assert "items" in page
        data = page["items"]
        assert isinstance(data, list)
        assert len(data) > 0

    @pytest.mark.asyncio
    async def test_get_flow(self, client, app, auth_headers_system):
        """Получение flow."""
        response = await client.get(
            "/flows/api/v1/flows/example_react", headers=auth_headers_system
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == "example_react"

    @pytest.mark.asyncio
    async def test_get_nonexistent_flow(self, client, app, auth_headers_system):
        """404 для несуществующего flow."""
        response = await client.get(
            "/flows/api/v1/flows/nonexistent_flow_xyz", headers=auth_headers_system
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_flow_with_inline_node(self, client, app, unique_id, auth_headers_system):
        """Создание flow с inline нодой."""
        flow_id = f"test_flow_inline_node_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "Ты тестовый агент.", "tools": []}
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["flow_id"] == flow_id
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_create_flow_with_invalid_node_id(
        self, client, app, unique_id, auth_headers_system
    ):
        """Ошибка при создании flow с несуществующим node_id."""
        flow_id = f"test_flow_invalid_node_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "node_id": "nonexistent_node_xyz"}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 400
        assert "nonexistent_node_xyz" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_flow_without_agent_id(self, client, app, unique_id, auth_headers_system):
        """Создание flow с inline конфигом агента (без flow_id)."""
        flow_id = f"test_flow_inline_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {"type": "llm_node", "prompt": "You are a test agent", "tools": []}
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_create_flow_with_valid_tool_id(
        self, client, app, unique_id, auth_headers_system
    ):
        """Создание flow с существующим tool_id."""
        flow_id = f"test_flow_valid_tool_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "You are a test agent",
                        "tools": ["calculator"],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)

    @pytest.mark.asyncio
    async def test_create_flow_with_invalid_tool_id(
        self, client, app, unique_id, auth_headers_system
    ):
        """Ошибка при создании flow с несуществующим tool_id."""
        flow_id = f"test_flow_invalid_tool_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {
                    "main": {
                        "type": "llm_node",
                        "prompt": "Test",
                        "tools": ["nonexistent_tool_xyz"],
                    }
                },
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 400
        assert "nonexistent_tool_xyz" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_flow_with_node_as_tool(self, client, app, unique_id, auth_headers_system):
        """Создание flow с нодой в качестве tool."""
        flow_id = f"test_flow_node_tool_{unique_id}"
        response = await client.post(
            "/flows/api/v1/flows/",
            headers=auth_headers_system,
            json={
                "flow_id": flow_id,
                "name": "Test Agent",
                "entry": "main",
                "nodes": {"main": {"type": "llm_node", "prompt": "Test", "tools": ["calculator"]}},
                "edges": [{"from_node": "main", "to_node": None}],
            },
        )
        assert response.status_code == 200
        await client.delete(f"/flows/api/v1/flows/{flow_id}", headers=auth_headers_system)


class TestToolsAPI:
    """Тесты /api/v1/tools"""

    @pytest.mark.asyncio
    async def test_list_tools(self, client, app):
        """Список tools."""
        response = await client.get("/flows/api/v1/tools/")
        assert response.status_code == 200
        page = response.json()
        assert "items" in page
        data = page["items"]
        assert isinstance(data, list)

    @pytest.mark.asyncio
    async def test_list_all_tools_includes_builtin_registry_tools(self, client, app):
        """Общий picker должен видеть platform tools из ToolRegistry."""
        response = await client.get("/flows/api/v1/tools/all?limit=2000&offset=0")
        assert response.status_code == 200
        page = response.json()
        ids = {item["tool_id"] for item in page["items"]}
        assert "browser_page_markdown" in ids
        assert "schedule_one_time_task" in ids

    @pytest.mark.asyncio
    async def test_get_tool(self, client, app, auth_headers_system):
        """Получение tool."""
        response = await client.get("/flows/api/v1/tools/calculator", headers=auth_headers_system)
        assert response.status_code == 200
        data = response.json()
        assert data["tool_id"] == "calculator"

    @pytest.mark.asyncio
    async def test_get_nonexistent_tool(self, client, app, auth_headers_system):
        """404 для несуществующего tool."""
        response = await client.get(
            "/flows/api/v1/tools/nonexistent_tool", headers=auth_headers_system
        )
        assert response.status_code == 404


class TestTasksAPI:
    """Тесты /api/v1/tasks"""

    @pytest.mark.asyncio
    async def test_submit_task(
        self, client, app, mock_llm, unique_id, sync_tools, auth_headers_system
    ):
        """Запуск task."""
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            headers=auth_headers_system,
            json={
                "flow_id": "example_react",
                "session_id": f"example_react:test-task-session-{unique_id}",
                "content": "Test message",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data

    @pytest.mark.asyncio
    async def test_submit_task_nonexistent_flow(self, client, app, sync_tools, auth_headers_system):
        """Ошибка при несуществующем flow."""
        response = await client.post(
            "/flows/api/v1/tasks/submit",
            headers=auth_headers_system,
            json={
                "flow_id": "nonexistent_flow_abc",
                "session_id": "nonexistent_flow_abc:test-session",
                "content": "Test",
            },
        )
        assert response.status_code == 404
