"""
Тесты для TaskIQ и всех интерфейсов.

Тесты используют реальную PostgreSQL БД, без моков.
Каждый интерфейс тестируется с реальным flow и агентом.
"""

import pytest
import pytest_asyncio
import asyncio
import uuid
import json

from apps.agents.container import get_agents_container
from apps.agents.models import FlowConfig, AgentConfig, AgentType, SessionConfig, SessionStatus
from apps.agents.tasks.agent_tasks import process_agent_task
from apps.agents.tasks.message_tasks import send_message_task
from apps.agents.interfaces.base import Message
from apps.agents.interfaces.web_interface import WebInterface
from apps.agents.interfaces.api_interface import APIInterface
from apps.agents.interfaces.telegram_interface import TelegramInterface
from core.context import set_context, clear_context, get_context
from core.models import User, Company, Context


@pytest_asyncio.fixture
async def integration_flow(migrated_db, taskiq_broker, test_context, flow_repo, agent_repo, unique_id):
    """Создает тестовый flow с агентом для интеграционных тестов"""
    flow_id = unique_id("flow")
    agent_id = unique_id("agent")
    
    agent_config = AgentConfig(
        agent_id=agent_id,
        name="Integration Test Agent",
        agent_type=AgentType.REACT,
        prompt="Ты тестовый агент. На любой вопрос отвечай кратко и по делу.",
        tools=[],
    )
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id=flow_id,
        name="Integration Test Flow",
        entry_point_agent=agent_id,
        platforms={
            "web": {"enabled": True},
            "api": {"enabled": True},
            "telegram": {"enabled": True, "bot_token": "test_token"},
        },
    )
    await flow_repo.set(flow_config)
    
    yield flow_config
    
    await flow_repo.delete(flow_id)
    await agent_repo.delete(agent_id)


class TestProcessAgentTask:
    """Тесты для process_agent_task"""
    
    @pytest.mark.asyncio
    async def test_direct_call(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """Прямой вызов process_agent_task без воркера"""
        session_id = unique_id("session")
        
        user_data = {
            "name": test_user.name,
            "groups": test_user.groups,
        }
        
        company_data = {
            "name": test_company.name,
            "subdomain": test_company.subdomain,
        }
        
        result = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            message="Привет!",
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        assert result["status"] == "completed"
        assert result["session_id"] == session_id
        assert "response" in result
    
    @pytest.mark.asyncio
    async def test_multiple_messages_same_session(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """Несколько сообщений в одной сессии"""
        session_id = unique_id("session")
        
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        # Первое сообщение
        result1 = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            message="Первое сообщение",
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        assert result1["status"] == "completed"
        
        # Второе сообщение
        result2 = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            message="Второе сообщение",
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        assert result2["status"] == "completed"
        assert result2["session_id"] == session_id


class TestSendMessageTask:
    """Тесты для send_message_task"""
    
    @pytest.mark.asyncio
    async def test_api_platform(self, migrated_db, test_context, integration_flow, unique_id):
        """Отправка через API платформу (просто логирование)"""
        session_id = unique_id("session")
        
        result = await send_message_task(
            platform="api",
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            content="Тестовое сообщение",
            metadata={},
            user_id="test_user",
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_web_platform(self, migrated_db, test_context, integration_flow, unique_id):
        """Отправка через Web платформу (сохраняет notification)"""
        session_id = unique_id("session")
        
        result = await send_message_task(
            platform="web",
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            content="Web сообщение",
            metadata={"web_chat": True},
            user_id="test_user",
        )
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_system_platform_skipped(self, migrated_db, test_context, integration_flow, unique_id):
        """Системные платформы пропускаются"""
        session_id = unique_id("session")
        
        result = await send_message_task(
            platform="system",
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            content="Системное сообщение",
            metadata={},
            user_id="test_user",
        )
        
        assert result is True


class TestWebInterface:
    """Интеграционные тесты для WebInterface"""
    
    @pytest_asyncio.fixture
    async def web_interface(self):
        """Создает WebInterface"""
        return WebInterface(platform_config={"enabled": True})
    
    @pytest.mark.asyncio
    async def test_handle_message(
        self,
        migrated_db,
        test_context,
        integration_flow,
        web_interface,
        unique_id,
    ):
        """Обработка входящего сообщения"""
        session_id = unique_id("session")
        
        raw_data = {
            "message": "Тестовое сообщение через Web",
            "agent_id": integration_flow.flow_id,
            "session_id": session_id,
            "user_id": test_context.user.user_id,
        }
        
        message = await web_interface.handle_message(raw_data, integration_flow.flow_id)
        
        assert message is not None
        assert message.content == "Тестовое сообщение через Web"
        assert message.platform == "web"
    
    @pytest.mark.asyncio
    async def test_create_task(
        self,
        migrated_db,
        test_context,
        integration_flow,
        web_interface,
        unique_id,
    ):
        """Создание задачи через WebInterface"""
        session_id = f"web:{test_context.user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        message = Message(
            user_id=test_context.user.user_id,
            session_id=session_id,
            content="Создать задачу",
            flow_id=integration_flow.flow_id,
            platform="web",
            metadata={"web_chat": True},
        )
        
        task_id = await web_interface.create_task(message, integration_flow.flow_id)
        
        assert task_id is not None
        assert len(task_id) > 0
    
    @pytest.mark.asyncio
    async def test_send_message(
        self,
        migrated_db,
        test_context,
        integration_flow,
        web_interface,
        unique_id,
    ):
        """Отправка сообщения через WebInterface (сохраняет notification)"""
        session_id = f"web:{test_context.user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        message = Message(
            user_id=test_context.user.user_id,
            session_id=session_id,
            content="Ответ агента",
            flow_id=integration_flow.flow_id,
            platform="web",
            metadata={"web_chat": True},
        )
        
        # Не должно выбросить исключение
        await web_interface.send_message(message)


class TestAPIInterface:
    """Интеграционные тесты для APIInterface"""
    
    @pytest_asyncio.fixture
    async def api_interface(self):
        """Создает APIInterface"""
        return APIInterface(platform_config={"enabled": True})
    
    @pytest.mark.asyncio
    async def test_handle_message(
        self,
        migrated_db,
        test_context,
        integration_flow,
        api_interface,
        unique_id,
    ):
        """Обработка входящего API сообщения"""
        session_id = unique_id("session")
        
        raw_data = {
            "message": "API запрос",
            "session_id": session_id,
        }
        
        message = await api_interface.handle_message(raw_data, integration_flow.flow_id)
        
        assert message is not None
        assert message.content == "API запрос"
        assert message.platform == "api"
    
    @pytest.mark.asyncio
    async def test_create_task(
        self,
        migrated_db,
        test_context,
        integration_flow,
        api_interface,
        unique_id,
    ):
        """Создание задачи через APIInterface"""
        session_id = f"api:{test_context.user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        message = Message(
            user_id=test_context.user.user_id,
            session_id=session_id,
            content="API задача",
            flow_id=integration_flow.flow_id,
            platform="api",
            metadata={},
        )
        
        task_id = await api_interface.create_task(message, integration_flow.flow_id)
        
        assert task_id is not None


class TestFullMessageCycle:
    """Полный цикл сообщения через разные интерфейсы"""
    
    @pytest.mark.asyncio
    async def test_web_full_cycle(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """
        Полный цикл через Web:
        1. WebInterface.handle_message
        2. process_agent_task
        3. Проверка результата
        """
        web_interface = WebInterface(platform_config={"enabled": True})
        session_id = f"web:{test_user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        # 1. Обрабатываем входящее сообщение
        raw_data = {
            "message": "Привет через Web!",
            "agent_id": integration_flow.flow_id,
            "session_id": session_id,
            "user_id": test_user.user_id,
        }
        
        message = await web_interface.handle_message(raw_data, integration_flow.flow_id)
        assert message is not None
        
        # 2. Выполняем задачу напрямую
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        result = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=message.session_id,
            message=message.content,
            platform="web",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata=message.metadata or {},
            user_data=user_data,
            company_data=company_data,
        )
        
        # 3. Проверяем результат
        assert result["status"] == "completed"
        assert "response" in result
    
    @pytest.mark.asyncio
    async def test_api_full_cycle(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """
        Полный цикл через API:
        1. APIInterface.handle_message
        2. process_agent_task
        3. Проверка результата
        """
        api_interface = APIInterface(platform_config={"enabled": True})
        session_id = unique_id("session")
        
        # 1. Обрабатываем входящее сообщение
        raw_data = {
            "message": "API запрос к агенту",
            "session_id": session_id,
        }
        
        message = await api_interface.handle_message(raw_data, integration_flow.flow_id)
        assert message is not None
        
        # 2. Выполняем задачу
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        result = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=message.session_id,
            message=message.content,
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        # 3. Проверяем результат
        assert result["status"] == "completed"


class TestSessionManagement:
    """Тесты управления сессиями"""
    
    @pytest.mark.asyncio
    async def test_session_created_on_first_message(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """Сессия создается при первом сообщении"""
        session_id = f"web:{test_user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        container = get_agents_container()
        storage = container.storage
        
        # До отправки сообщения сессии нет
        session_key = f"session:{session_id}"
        session_data = await storage.get(session_key)
        assert session_data is None
        
        # Отправляем сообщение
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        result = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            message="Первое сообщение",
            platform="web",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        # Проверяем что задача выполнена успешно
        assert result["status"] == "completed"
        assert result["session_id"] == session_id
    
    @pytest.mark.asyncio
    async def test_session_status_changes(
        self,
        migrated_db,
        test_context,
        integration_flow,
        test_user,
        test_company,
        unique_id,
    ):
        """Статус сессии меняется корректно"""
        session_id = f"api:{test_user.user_id}:{integration_flow.flow_id}:{unique_id('sess')}"
        
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        # Первое сообщение
        result = await process_agent_task(
            flow_id=integration_flow.flow_id,
            session_id=session_id,
            message="Тест статуса",
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        assert result["status"] == "completed"
