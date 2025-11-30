"""
Тесты для API истории сессий.

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
async def test_agent_for_history(agent_repo, unique_id, test_context) -> AgentConfig:
    """Тестовый агент для истории"""
    agent_id = unique_id("hist_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="History Test Agent",
        description="Agent for history testing",
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
async def test_flow_for_history(flow_repo, test_agent_for_history, unique_id, test_context) -> FlowConfig:
    """Тестовый flow для истории"""
    flow_id = unique_id("hist_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="History Test Flow",
        description="Flow for history testing",
        entry_point_agent=test_agent_for_history.agent_id,
        source="test"
    )
    await flow_repo.set(flow)
    yield flow
    await flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_session(session_repo, test_flow_for_history, unique_id, test_context) -> SessionConfig:
    """Тестовая сессия"""
    session_id = unique_id("session")
    session = SessionConfig(
        session_id=session_id,
        flow_id=test_flow_for_history.flow_id,
        platform="test",
        user_id="test_user",
        status=SessionStatus.ACTIVE
    )
    await session_repo.set(session)
    yield session
    await session_repo.delete(session_id)


class TestSessionsListAPI:
    """Тесты для GET /frontend/api/history/sessions endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_sessions(self, frontend_client, test_session):
        """Проверяем получение списка сессий"""
        response = await frontend_client.get("/frontend/api/history/sessions")
        
        assert response.status_code == 200
        data = response.json()
        
        # SessionListResponse структура
        assert "sessions" in data or isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_list_sessions_by_platform(self, frontend_client, test_session):
        """Проверяем фильтрацию по платформе"""
        response = await frontend_client.get("/frontend/api/history/sessions?platform=test")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_list_sessions_with_limit(self, frontend_client, test_session):
        """Проверяем лимит"""
        response = await frontend_client.get("/frontend/api/history/sessions?limit=10")
        
        assert response.status_code == 200


class TestSessionMessagesAPI:
    """Тесты для GET /frontend/api/history/sessions/{session_id}/messages endpoint"""
    
    @pytest.mark.asyncio
    async def test_get_session_messages(self, frontend_client, test_session):
        """Проверяем получение сообщений сессии"""
        response = await frontend_client.get(
            f"/frontend/api/history/sessions/{test_session.session_id}/messages"
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # MessageHistoryResponse структура
        assert "messages" in data or isinstance(data, list)
    
    @pytest.mark.asyncio
    async def test_get_session_messages_with_checkpoints(self, frontend_client, test_session):
        """Проверяем получение сообщений с чекпоинтами"""
        response = await frontend_client.get(
            f"/frontend/api/history/sessions/{test_session.session_id}/messages?include_checkpoints=true"
        )
        
        assert response.status_code == 200
