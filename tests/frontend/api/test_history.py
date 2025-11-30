"""
Тесты для API истории сессий.

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
async def test_agent_for_history(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент"""
    agent_id = make_unique_id("hist_agent")
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
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_flow_for_history(frontend_flow_repo, test_agent_for_history, frontend_client) -> FlowConfig:
    """Тестовый flow"""
    flow_id = make_unique_id("hist_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="History Test Flow",
        description="Flow for history testing",
        entry_point_agent=test_agent_for_history.agent_id,
        source="test"
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_session(frontend_session_repo, test_flow_for_history, frontend_client) -> SessionConfig:
    """Тестовая сессия"""
    session_id = make_unique_id("session")
    session = SessionConfig(
        session_id=session_id,
        flow_id=test_flow_for_history.flow_id,
        platform="test",
        user_id="test_user",
        status=SessionStatus.ACTIVE
    )
    await frontend_session_repo.set(session)
    yield session
    await frontend_session_repo.delete(session_id)


class TestSessionsListAPI:
    """Тесты для GET /frontend/api/history/sessions endpoint"""
    
    @pytest.mark.asyncio
    async def test_list_sessions(self, frontend_client, test_session):
        """Проверяем получение списка сессий"""
        response = await frontend_client.get("/frontend/api/history/sessions")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        assert "sessions" in data
    
    @pytest.mark.asyncio
    async def test_list_sessions_by_platform(self, frontend_client, test_session):
        """Проверяем фильтрацию по платформе"""
        response = await frontend_client.get(
            "/frontend/api/history/sessions?platform=test"
        )
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_list_sessions_with_limit(self, frontend_client, test_session):
        """Проверяем лимит"""
        response = await frontend_client.get(
            "/frontend/api/history/sessions?limit=5"
        )
        
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
        assert "messages" in data
    
    @pytest.mark.asyncio
    async def test_get_session_messages_with_checkpoints(self, frontend_client, test_session):
        """Проверяем получение сообщений с чекпоинтами"""
        response = await frontend_client.get(
            f"/frontend/api/history/sessions/{test_session.session_id}/messages?include_checkpoints=true"
        )
        
        assert response.status_code == 200
