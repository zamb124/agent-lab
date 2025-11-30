"""
Тесты для API агентов (graph endpoints).

Используется реальная БД без моков.
"""

import uuid
import pytest
import pytest_asyncio

from apps.agents.models import (
    AgentConfig,
    AgentType,
    CodeMode,
    GraphDefinition,
    GraphNode,
    GraphEdge,
    LLMConfig,
)


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_agent(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для тестов graph API"""
    agent_id = make_unique_id("agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Test Graph Agent",
        description="Agent for testing graph endpoints",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a test agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test",
        graph_definition=None
    )
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_agent_with_graph(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент с graph_definition"""
    agent_id = make_unique_id("agent_graph")
    
    graph_def = GraphDefinition(
        nodes=[
            GraphNode(
                id="start_node",
                type="agent_node",
                params={"name": "Start", "ui": {"x": 100, "y": 100, "width": 200, "height": 100}},
                code_mode="code_reference"
            ),
            GraphNode(
                id="process_node",
                type="tool_node",
                params={"name": "Process", "ui": {"x": 400, "y": 100, "width": 200, "height": 100}},
                code_mode="code_reference"
            )
        ],
        edges=[
            GraphEdge(source="START", target="start_node"),
            GraphEdge(source="start_node", target="process_node")
        ],
        entry_point="start_node"
    )
    
    agent = AgentConfig(
        agent_id=agent_id,
        name="Test Agent With Graph",
        description="Agent with predefined graph",
        type=AgentType.STATEGRAPH,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a stategraph agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test",
        graph_definition=graph_def
    )
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


class TestAgentsListAPI:
    """Тесты для GET /frontend/api/agents/ endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_agents_returns_agents(
        self, frontend_client, test_agent, agent_repo
    ):
        """Проверяем получение списка агентов"""
        response = await frontend_client.get("/frontend/api/agents/")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_agents_with_limit(
        self, frontend_client, test_agent
    ):
        """Проверяем лимит при получении списка"""
        response = await frontend_client.get("/frontend/api/agents/?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) <= 5


class TestAgentGraphAPI:
    """Тесты для GET/PUT /frontend/api/agents/{agent_id}/graph endpoints"""
    
    @pytest.mark.asyncio
    async def test_get_graph_empty(self, frontend_client, test_agent):
        """Проверяем получение пустого графа"""
        response = await frontend_client.get(f"/frontend/api/agents/{test_agent.agent_id}/graph")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["agent_id"] == test_agent.agent_id
        assert data["nodes"] == []
        assert data["edges"] == []
        assert data["entry_point"] is None
    
    @pytest.mark.asyncio
    async def test_get_graph_with_definition(self, frontend_client, test_agent_with_graph):
        """Проверяем получение графа с definition"""
        response = await frontend_client.get(f"/frontend/api/agents/{test_agent_with_graph.agent_id}/graph")
        
        assert response.status_code == 200
        data = response.json()
        
        assert data["agent_id"] == test_agent_with_graph.agent_id
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 2
        assert data["entry_point"] == "start_node"
    
    @pytest.mark.asyncio
    async def test_get_graph_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего агента"""
        response = await frontend_client.get("/frontend/api/agents/nonexistent_agent/graph")
        
        assert response.status_code == 404
    
    @pytest.mark.asyncio
    async def test_update_graph(self, frontend_client, test_agent, agent_repo):
        """Проверяем обновление графа агента"""
        graph_data = {
            "nodes": [
                {
                    "id": "new_node_1",
                    "type": "agent_node",
                    "params": {"name": "Node 1"},
                    "code_mode": "code_reference",
                    "ui": {"x": 50, "y": 50, "width": 150, "height": 80}
                },
                {
                    "id": "new_node_2",
                    "type": "tool_node",
                    "params": {"name": "Node 2"},
                    "code_mode": "code_reference",
                    "ui": {"x": 300, "y": 50, "width": 150, "height": 80}
                }
            ],
            "edges": [
                {"source": "START", "target": "new_node_1"},
                {"source": "new_node_1", "target": "new_node_2"}
            ],
            "entry_point": "new_node_1"
        }
        
        response = await frontend_client.put(
            f"/frontend/api/agents/{test_agent.agent_id}/graph",
            json=graph_data
        )
        
        assert response.status_code == 200
        assert response.json()["message"] == "Agent graph updated successfully"
    
    @pytest.mark.asyncio
    async def test_update_graph_not_found(self, frontend_client):
        """Проверяем 404 при обновлении несуществующего агента"""
        graph_data = {
            "nodes": [],
            "edges": [],
            "entry_point": ""
        }
        
        response = await frontend_client.put(
            "/frontend/api/agents/nonexistent_agent/graph",
            json=graph_data
        )
        
        assert response.status_code == 404
