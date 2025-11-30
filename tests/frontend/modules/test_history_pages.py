"""
Тесты для модуля History (страницы истории сессий).

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
async def test_agent_for_history_page(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для истории"""
    agent_id = make_unique_id("hist_page_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="History Page Test Agent",
        description="Agent for history page testing",
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
async def test_flow_for_history_page(frontend_flow_repo, test_agent_for_history_page, frontend_client) -> FlowConfig:
    """Тестовый flow для истории"""
    flow_id = make_unique_id("hist_page_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="History Page Test Flow",
        description="Flow for history page testing",
        entry_point_agent=test_agent_for_history_page.agent_id,
        source="test"
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


@pytest_asyncio.fixture
async def test_session_for_history_page(frontend_session_repo, test_flow_for_history_page, frontend_client) -> SessionConfig:
    """Тестовая сессия для истории"""
    session_id = make_unique_id("hist_page_session")
    session = SessionConfig(
        session_id=session_id,
        flow_id=test_flow_for_history_page.flow_id,
        platform="test",
        user_id="test_user",
        status=SessionStatus.ACTIVE
    )
    await frontend_session_repo.set(session)
    yield session
    await frontend_session_repo.delete(session_id)


class TestHistoryPageRoutes:
    """Тесты для страниц History"""
    
    @pytest.mark.asyncio
    async def test_history_main_page(self, frontend_client):
        """Проверяем главную страницу истории"""
        response = await frontend_client.get("/frontend/history/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_history_sessions_table(self, frontend_client, test_session_for_history_page):
        """Проверяем таблицу сессий"""
        response = await frontend_client.get("/frontend/history/sessions")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_history_sessions_with_filters(self, frontend_client):
        """Проверяем фильтрацию сессий"""
        response = await frontend_client.get(
            "/frontend/history/sessions?platform=test&limit=10"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_session_messages_modal(self, frontend_client, test_session_for_history_page):
        """Проверяем модалку с сообщениями"""
        response = await frontend_client.get(
            f"/frontend/history/sessions/{test_session_for_history_page.session_id}/messages"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
