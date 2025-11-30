"""
Тесты для API flows.

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import FlowConfig, AgentConfig, AgentType, CodeMode, LLMConfig


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_agent_for_flow(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для привязки к flow"""
    from core.context import set_context
    set_context(frontend_client.test_context)
    
    agent_id = make_unique_id("entry_agent")
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
    await frontend_agent_repo.set(agent)
    yield agent
    set_context(frontend_client.test_context)
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow(frontend_flow_repo, test_agent_for_flow, frontend_client) -> FlowConfig:
    """Тестовый flow для тестов"""
    from core.context import set_context
    set_context(frontend_client.test_context)
    
    flow_id = make_unique_id("flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test Flow",
        description="Flow for testing",
        entry_point_agent=test_agent_for_flow.agent_id,
        source="test",
        canvas_data=None
    )
    await frontend_flow_repo.set(flow)
    yield flow
    set_context(frontend_client.test_context)
    await frontend_flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_flow_with_canvas(frontend_flow_repo, test_agent_for_flow, frontend_client) -> FlowConfig:
    """Тестовый flow с canvas_data"""
    from core.context import set_context
    set_context(frontend_client.test_context)
    
    flow_id = make_unique_id("flow_canvas")
    
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
    await frontend_flow_repo.set(flow)
    yield flow
    set_context(frontend_client.test_context)
    await frontend_flow_repo.delete(flow_id)


class TestFlowsListAPI:
    """Тесты для GET /frontend/api/flows/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_flows_returns_flows(self, frontend_client, test_flow):
        """Проверяем получение списка flows"""
        response = await frontend_client.get("/frontend/api/flows/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_flows_with_pagination(self, frontend_client, test_flow):
        """Проверяем пагинацию"""
        response = await frontend_client.get("/frontend/api/flows/?limit=5&offset=0")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5


class TestFlowDetailAPI:
    """Тесты для GET /frontend/api/flows/{flow_id} endpoint"""

    @pytest.mark.asyncio
    async def test_get_flow_by_id(self, frontend_client, test_flow):
        """Проверяем получение flow по ID"""
        response = await frontend_client.get(f"/frontend/api/flows/{test_flow.flow_id}")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["flow_id"] == test_flow.flow_id

    @pytest.mark.asyncio
    async def test_get_flow_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get("/frontend/api/flows/nonexistent_flow")
        
        assert response.status_code == 404


class TestFlowCreateAPI:
    """Тесты для создания flows"""
    
    @pytest.mark.asyncio
    async def test_create_flow(self, frontend_client, test_agent_for_flow, flow_repo):
        """Проверяем создание нового flow"""
        flow_id = make_unique_id("new_flow")
        
        flow_data = {
            "flow_id": flow_id,
            "name": "New Test Flow",
            "description": "Created via API",
            "entry_point_agent": test_agent_for_flow.agent_id,
            "source": "test"
        }
        
        response = await frontend_client.post("/frontend/api/flows/", json=flow_data)
        
        assert response.status_code == 200
        
        # Очистка
        await flow_repo.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_create_flow_without_entry_agent(self, frontend_client, flow_repo):
        """Проверяем создание flow без entry_point_agent"""
        flow_id = make_unique_id("flow_no_agent")
        
        flow_data = {
            "flow_id": flow_id,
            "name": "Flow Without Agent",
            "source": "test"
        }
        
        response = await frontend_client.post("/frontend/api/flows/", json=flow_data)
        
        assert response.status_code == 200
        
        # Очистка
        await flow_repo.delete(flow_id)


class TestFlowCanvasAPI:
    """Тесты для canvas endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_canvas_data_empty(self, frontend_client, test_flow):
        """Проверяем получение пустых canvas данных"""
        response = await frontend_client.get(f"/frontend/api/flows/{test_flow.flow_id}/canvas")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["flow_id"] == test_flow.flow_id
    
    @pytest.mark.asyncio
    async def test_get_canvas_data_with_content(self, frontend_client, test_flow_with_canvas):
        """Проверяем получение canvas данных с содержимым"""
        response = await frontend_client.get(
            f"/frontend/api/flows/{test_flow_with_canvas.flow_id}/canvas"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["flow_id"] == test_flow_with_canvas.flow_id
    
    @pytest.mark.asyncio
    async def test_get_canvas_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего flow"""
        response = await frontend_client.get("/frontend/api/flows/nonexistent_flow/canvas")
        
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
