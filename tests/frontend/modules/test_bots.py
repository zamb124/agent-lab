"""
Тесты для модуля Bots (страницы управления ботами).

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
async def test_agent_for_bot(frontend_agent_repo, frontend_client) -> AgentConfig:
    """Тестовый агент для бота"""
    agent_id = make_unique_id("bot_agent")
    agent = AgentConfig(
        agent_id=agent_id,
        name="Bot Entry Agent",
        description="Agent for bot testing",
        type=AgentType.REACT,
        code_mode=CodeMode.CODE_REFERENCE,
        prompt="You are a helpful bot",
        tools=[],
        llm_config=LLMConfig(model="mock-gpt-4", context_window=10000),
        source="test"
    )
    await frontend_agent_repo.set(agent)
    yield agent
    await frontend_agent_repo.delete(agent_id)


@pytest_asyncio.fixture
async def test_bot(frontend_flow_repo, test_agent_for_bot, frontend_client) -> FlowConfig:
    """Тестовый бот (flow)"""
    flow_id = make_unique_id("bot")
    flow = FlowConfig(
        flow_id=flow_id,
        name="Test Bot",
        description="Bot for testing",
        entry_point_agent=test_agent_for_bot.agent_id,
        source="test",
        platforms={"telegram": {"username": "test_bot"}}
    )
    await frontend_flow_repo.set(flow)
    yield flow
    await frontend_flow_repo.delete(flow_id)


class TestBotsPageRoutes:
    """Тесты для страниц модуля Bots"""
    
    @pytest.mark.asyncio
    async def test_bots_main_page(self, frontend_client):
        """Проверяем главную страницу ботов"""
        response = await frontend_client.get("/frontend/bots/")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_bots_list(self, frontend_client, test_bot):
        """Проверяем список ботов"""
        response = await frontend_client.get("/frontend/bots/list")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_bot_details_existing(self, frontend_client, test_bot):
        """Проверяем детали существующего бота"""
        response = await frontend_client.get(f"/frontend/bots/{test_bot.flow_id}/details")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_bot_details_new(self, frontend_client):
        """Проверяем форму создания нового бота"""
        response = await frontend_client.get("/frontend/bots/new/details")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_bot_details_not_found(self, frontend_client):
        """Проверяем 404 для несуществующего бота"""
        response = await frontend_client.get("/frontend/bots/nonexistent_bot/details")
        
        assert response.status_code == 404


class TestBotsPlatformFields:
    """Тесты для динамических полей платформ"""
    
    @pytest.mark.asyncio
    async def test_platform_fields_whatsapp(self, frontend_client):
        """Проверяем поля для WhatsApp"""
        response = await frontend_client.get("/frontend/bots/platform-fields/whatsapp")
        
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
    
    @pytest.mark.asyncio
    async def test_platform_fields_telegram(self, frontend_client):
        """Проверяем поля для Telegram"""
        response = await frontend_client.get("/frontend/bots/platform-fields/telegram")
        
        assert response.status_code == 200
    
    @pytest.mark.asyncio
    async def test_platform_fields_unsupported(self, frontend_client):
        """Проверяем ответ для неподдерживаемой платформы"""
        response = await frontend_client.get("/frontend/bots/platform-fields/unknown")
        
        assert response.status_code == 404
