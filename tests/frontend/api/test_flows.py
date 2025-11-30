"""
Тесты для API flows.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig, AgentConfig, AgentType, CodeMode, LLMConfig


@pytest_asyncio.fixture
async def test_agent_for_flow(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый агент для привязки к flow"""
    agent_id = unique_id("entry_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Entry Point Agent",
        description="Agent for flow entry point",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are an entry point agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await agent_repo.set(agent)
    yield agent
    await agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow(flow_repo, test_agent_for_flow, unique_id, test_context) -> FlowConfig:
    """Тестовый flow для тестов"""
    flow_id = unique_id("flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test Flow",
        description="Flow for testing",
        entry_point_agent=test_agent_for_flow.agent_id,
        source="test",
        canvas_data=None
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_flow_with_canvas(flow_repo, test_agent_for_flow, unique_id, test_context) -> FlowConfig:
    """Тестовый flow с canvas_data"""
    flow_id = unique_id("flow_canvas")
    
    canvas_data = {
        "nodes": [
            {
                "id": "flow_node_1",
                "type": "flow_node",
                "params": {"flow_id": flow_id, "name": "Main Flow"},
                "ui": {"x": 50, "y": 50}
            },
            {
                "id": "agent_node_1",
                "type": "agent_node",
                "params": {"agent_id": test_agent_for_flow.agent_id, "name": "Entry Agent"},
                "ui": {"x": 250, "y": 50}
            }
        ],
        "edges": [
            {"source": "flow_node_1", "target": "agent_node_1"}
        ]
    }
    
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test Flow With Canvas",
        description="Flow with predefined canvas",
        entry_point_agent=test_agent_for_flow.agent_id,
        source="test",
        canvas_data=canvas_data
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


class TestFlowsListAPI:
    """Тесты для GET /frontend/api/flows/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_flows_returns_flows(self, frontend_client, test_flow):
        """Проверяем получение списка flows"""
        response = await frontend_client.get("/frontend/api/flows/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        flow_ids = [f["flow_id"] for f in data]
        assert test_flow.flow_id in flow_ids
    
    @pytest.mark.asyncio
    async def test_list_flows_with_limit(self, frontend_client, test_flow):
        """Проверяем лимит"""
        response = await frontend_client.get("/frontend/api/flows/?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5


class TestFlowCanvasAPI:
    """Тесты для canvas endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_canvas_data_empty(self, frontend_client, test_flow):
        """Проверяем получение пустых canvas данных"""
        response = await frontend_client.get(f"/frontend/api/flows/{test_flow.flow_id}/canvas")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["flow_id"] == test_flow.flow_id
        assert data["nodes"] == []
        assert data["edges"] == []
    
    @pytest.mark.asyncio
    async def test_get_canvas_data_with_content(self, frontend_client, test_flow_with_canvas):
        """Проверяем получение canvas данных с содержимым"""
        response = await frontend_client.get(
            f"/frontend/api/flows/{test_flow_with_canvas.flow_id}/canvas"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["flow_id"] == test_flow_with_canvas.flow_id
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1
    
    @pytest.mark.asyncio
    async def test_get_canvas_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get("/frontend/api/flows/nonexistent_flow/canvas")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_save_canvas_data(self, frontend_client, test_flow, flow_repo):
        """Проверяем сохранение canvas данных"""
        canvas_data = {
            "nodes": [
                {
                    "id": "new_flow_node",
                    "type": "flow_node",
                    "params": {"flow_id": test_flow.flow_id},
                    "ui": {"x": 100, "y": 100}
                }
            ],
            "edges": []
        }
        
        response = await frontend_client.put(
            f"/frontend/api/flows/{test_flow.flow_id}/canvas",
            json=canvas_data
        )
        
        assert response.status_code == 200
        
        updated_flow = await flow_repo.get(test_flow.flow_id)
        assert updated_flow.canvas_data is not None
        assert len(updated_flow.canvas_data.get("nodes", [])) == 1
    
    @pytest.mark.asyncio
    async def test_save_canvas_not_found(self, frontend_client):
        """Проверяем 404 при сохранении для несуществующего flow"""
        response = await frontend_client.put(
            "/frontend/api/flows/nonexistent_flow/canvas",
            json={"nodes": [], "edges": []}
        )
        
        assert response.status_code == 404


class TestFlowVariablesAPI:
    """Тесты для endpoints переменных flow"""
    
    @pytest.mark.asyncio
    async def test_get_flow_variables_empty(self, frontend_client, test_flow):
        """Проверяем получение пустых переменных"""
        response = await frontend_client.get(
            f"/frontend/api/flows/{test_flow.flow_id}/variables"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_flow_variables_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get(
            "/frontend/api/flows/nonexistent_flow/variables"
        )
        
        assert response.status_code == 404


class TestFlowCreateAPI:
    """Тесты для создания flows"""
    
    @pytest.mark.asyncio
    async def test_create_flow(self, frontend_client, test_agent_for_flow, flow_repo, unique_id):
        """Проверяем создание нового flow"""
        flow_id = unique_id("new_flow")
        
        flow_data = {
            "flow_id": flow_id,
            "name": "New Test Flow",
            "description": "Created via API",
            "entry_point_agent": test_agent_for_flow.agent_id,
            "source": "test"
        }
        
        response = await frontend_client.post("/frontend/api/flows/", json=flow_data)
        
        assert response.status_code == 200
        
        created_flow = await flow_repo.get(flow_id)
        assert created_flow is not None
        assert created_flow.name == "New Test Flow"
        
        await flow_repo.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_create_flow_without_entry_agent(self, frontend_client, flow_repo, unique_id):
        """Проверяем создание flow без entry_point_agent (должен работать)"""
        flow_id = unique_id("flow_no_agent")
        
        flow_data = {
            "flow_id": flow_id,
            "name": "Flow Without Agent",
            "source": "test"
        }
        
        response = await frontend_client.post("/frontend/api/flows/", json=flow_data)
        
        assert response.status_code == 200
        
        created_flow = await flow_repo.get(flow_id)
        assert created_flow is not None
        
        await flow_repo.delete(flow_id)
