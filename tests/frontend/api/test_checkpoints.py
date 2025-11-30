"""
Тесты для API checkpoints.

Используется реальная БД без моков.
"""

import pytest
import pytest_asyncio

from apps.agents.models import (
    FlowConfig,
    AgentConfig,
    AgentType,
    CodeMode,
    LLMConfig,
    SessionConfig,
    SessionStatus,
)


@pytest_asyncio.fixture
async def test_agent_for_checkpoints(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый агент для checkpoints"""
    agent_id = unique_id("cp_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Checkpoint Test Agent",
        description="Agent for checkpoint testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a test agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await agent_repo.set(agent)
    yield agent
    await agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow_for_checkpoints(flow_repo, test_agent_for_checkpoints, unique_id, test_context) -> FlowConfig:
    """Тестовый flow для checkpoints"""
    flow_id = unique_id("cp_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Checkpoint Test Flow",
        description="Flow for checkpoint testing",
        entry_point_agent=test_agent_for_checkpoints.agent_id,
        source="test"
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_session_for_checkpoints(session_repo, test_flow_for_checkpoints, unique_id, test_context) -> SessionConfig:
    """Тестовая сессия для checkpoints"""
    session_id = unique_id("cp_session")
    session = SessionConfig(
        session_id=session_id,
        flow_id=test_flow_for_checkpoints.flow_id,
        platform="test",
        user_id="test_user",
        status=SessionStatus.ACTIVE
    )
    await session_repo.set(session)
    yield session
    await session_repo.delete(session_id)


class TestCheckpointsTimelineAPI:
    """Тесты для GET /frontend/api/checkpoints/timeline/{thread_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_timeline(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение timeline для сессии"""
        response = await frontend_client.get(
            f"/frontend/api/checkpoints/timeline/{test_session_for_checkpoints.session_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "thread_id" in data
        assert "tree" in data
        assert "summary" in data
    
    @pytest.mark.asyncio
    async def test_get_timeline_without_values(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение timeline без значений"""
        response = await frontend_client.get(
            f"/frontend/api/checkpoints/timeline/{test_session_for_checkpoints.session_id}?include_values=false"
        )
        
        assert response.status_code == 200


class TestCheckpointsHistoryAPI:
    """Тесты для GET /frontend/api/checkpoints/history/{thread_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_history(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение истории checkpoints"""
        response = await frontend_client.get(
            f"/frontend/api/checkpoints/history/{test_session_for_checkpoints.session_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "thread_id" in data
        assert "history" in data


class TestCheckpointsConnectionsAPI:
    """Тесты для GET /frontend/api/checkpoints/connections/{thread_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_connections(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение связей между checkpoints"""
        response = await frontend_client.get(
            f"/frontend/api/checkpoints/connections/{test_session_for_checkpoints.session_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, dict)
