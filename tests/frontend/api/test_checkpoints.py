"""
Тесты для API checkpoints.

Используется реальная БД без моков.
"""

import uuid
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


def make_unique_id(prefix: str) -> str:
    """Генерирует уникальный ID"""
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


@pytest_asyncio.fixture
async def test_agent_for_checkpoints(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент"""
    agent_id = make_unique_id("cp_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Checkpoints Test Agent",
        description="Agent for checkpoints testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a test agent",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow_for_checkpoints(frontend_flow_repo, test_agent_for_checkpoints, frontend_client) -> FlowConfig:
    """Тестовый flow"""
    flow_id = make_unique_id("cp_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Checkpoints Test Flow",
        description="Flow for checkpoints testing",
        entry_point_agent=test_agent_for_checkpoints.agent_id,
        source="test"
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_session_for_checkpoints(frontend_session_repo, test_flow_for_checkpoints, frontend_client) -> SessionConfig:
    """Тестовая сессия"""
    session_id = make_unique_id("cp_session")
    session = SessionConfig(
        session_id=session_id,
        flow_id=test_flow_for_checkpoints.flow_id,
        platform="test",
        user_id="test_user",
        status=SessionStatus.ACTIVE
    )
    await frontend_session_repo.set(session)
    yield session
    await frontend_session_repo.delete(session_id)


class TestCheckpointsTimelineAPI:
    """Тесты для GET /frontend/api/v1/checkpoints/timeline/{thread_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_timeline(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение timeline"""
        response = await frontend_client.get(
            f"/frontend/api/v1/checkpoints/timeline/{test_session_for_checkpoints.session_id}"
        )
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
    
    @pytest.mark.asyncio
    async def test_get_timeline_without_values(self, frontend_client, test_session_for_checkpoints):
        """Проверяем timeline без значений"""
        response = await frontend_client.get(
            f"/frontend/api/v1/checkpoints/timeline/{test_session_for_checkpoints.session_id}?include_values=false"
        )
        
        assert response.status_code == 200


class TestCheckpointsConnectionsAPI:
    """Тесты для GET /frontend/api/v1/checkpoints/connections/{thread_id} endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_connections(self, frontend_client, test_session_for_checkpoints):
        """Проверяем получение connections"""
        response = await frontend_client.get(
            f"/frontend/api/v1/checkpoints/connections/{test_session_for_checkpoints.session_id}"
        )
        
        assert response.status_code == 200
