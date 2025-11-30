"""
Тесты для модуля Builder (визуальный редактор flows).

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
async def test_agent_for_builder(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для builder"""
    agent_id = make_unique_id("builder_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Builder Test Agent",
        description="Agent for builder testing",
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
async def test_flow_for_builder(frontend_flow_repo, test_agent_for_builder, frontend_client) -> FlowConfig:
    """Тестовый flow для builder"""
    flow_id = make_unique_id("builder_flow")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Builder Test Flow",
        description="Flow for builder testing",
        entry_point_agent=test_agent_for_builder.agent_id,
        source="test"
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


class TestBuilderPageRoutes:
    """Тесты для страниц Builder"""
    
    @pytest.mark.asyncio
    async def test_builder_index(self, frontend_client):
        """Проверяем главную страницу Builder"""
        response = await frontend_client.get("/frontend/builder/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_builder_flow_page(self, frontend_client, test_flow_for_builder):
        """Проверяем страницу редактирования flow"""
        response = await frontend_client.get(
            f"/frontend/builder/flow/{test_flow_for_builder.flow_id}"
        )
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_builder_new_flow(self, frontend_client):
        """Проверяем страницу создания нового flow"""
        response = await frontend_client.get("/frontend/builder/flow/new")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
