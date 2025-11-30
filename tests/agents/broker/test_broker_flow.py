"""
Тесты базовой функциональности TaskIQ брокера.

Проверяет:
1. Подключение к брокеру
2. Отправка задач через kiq
3. Уведомления WebInterface
4. Синхронизация session_id

Запуск:
    uv run pytest tests/agents/broker/test_broker_flow.py -v -s
"""

import pytest
import pytest_asyncio
import asyncio
import json

from apps.agents.container import get_agents_container
from apps.agents.models import FlowConfig, AgentConfig, AgentType
from apps.agents.tasks.agent_tasks import process_agent_task
from apps.agents.interfaces.base import Message
from apps.agents.interfaces.web_interface import WebInterface


@pytest_asyncio.fixture
async def broker_test_flow(migrated_db, taskiq_broker, test_context, flow_repo, agent_repo, unique_id):
    """Создает тестовый flow для тестов брокера"""
    flow_id = unique_id("broker_flow")
    agent_id = unique_id("broker_agent")
    
    agent_config = AgentConfig(
        agent_id=agent_id,
        name="Broker Test Agent",
        agent_type=AgentType.REACT,
        prompt="Ты тестовый агент для проверки брокера. Отвечай кратко: OK + повтор вопроса.",
        tools=[],
    )
    await agent_repo.set(agent_config)
    
    flow_config = FlowConfig(
        flow_id=flow_id,
        name="Broker Test Flow",
        entry_point_agent=agent_id,
        platforms={
            "web": {"enabled": True},
            "api": {"enabled": True},
        },
    )
    await flow_repo.set(flow_config)
    
    yield flow_config
    
    await flow_repo.delete(flow_id)
    await agent_repo.delete(agent_id)


class TestBrokerConnection:
    """Тесты подключения к брокеру"""
    
    @pytest.mark.asyncio
    async def test_broker_startup(self, migrated_db, taskiq_broker):
        """Брокер должен запуститься без ошибок"""
        from core.tasks.broker import broker
        
        assert broker is not None
        
        dsn = broker.dsn
        if callable(dsn):
            dsn = dsn()
        assert "localhost" in dsn or "postgres" in dsn
        assert "shared_db" in dsn
        print(f"✅ Брокер подключен к: {dsn[:50]}...")
    
    @pytest.mark.asyncio
    async def test_broker_is_initialized(self, migrated_db, taskiq_broker):
        """Брокер должен быть инициализирован после startup"""
        assert taskiq_broker is not None
        print("✅ Брокер инициализирован")


class TestTaskQueueing:
    """Тесты постановки задач в очередь"""
    
    @pytest.mark.asyncio
    async def test_task_kiq_returns_task(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
        test_company,
        unique_id,
    ):
        """kiq должен вернуть task и не выбросить исключение"""
        session_id = unique_id("session")
        
        user_data = {"name": test_user.name, "groups": test_user.groups}
        company_data = {"name": test_company.name, "subdomain": test_company.subdomain}
        
        task = await process_agent_task.kiq(
            flow_id=broker_test_flow.flow_id,
            session_id=session_id,
            message="Тест очереди",
            platform="api",
            user_id=test_user.user_id,
            company_id=test_company.company_id,
            metadata={},
            user_data=user_data,
            company_data=company_data,
        )
        
        assert task is not None
        assert task.task_id is not None
        print(f"✅ Задача создана: task_id={task.task_id}")
    
    @pytest.mark.asyncio
    async def test_web_interface_create_task(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
        unique_id,
    ):
        """WebInterface.create_task должен поставить задачу в очередь"""
        web_interface = WebInterface(platform_config={"enabled": True})
        session_id = f"web:{test_user.user_id}:{broker_test_flow.flow_id}:{unique_id('sess')}"
        
        message = Message(
            user_id=test_user.user_id,
            session_id=session_id,
            content="Тест через WebInterface",
            flow_id=broker_test_flow.flow_id,
            platform="web",
            metadata={"web_chat": True},
        )
        
        task_id = await web_interface.create_task(message, broker_test_flow.flow_id)
        
        assert task_id is not None
        print(f"✅ WebInterface создал задачу: task_id={task_id}")


class TestWebNotifications:
    """Тесты уведомлений WebInterface"""
    
    @pytest.mark.asyncio
    async def test_user_message_saved_as_notification(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
        unique_id,
    ):
        """USER_MESSAGE сохраняется как notification"""
        web_interface = WebInterface(platform_config={"enabled": True})
        session_uuid = unique_id("sess")
        
        raw_data = {
            "message": "Тестовое сообщение пользователя",
            "agent_id": broker_test_flow.flow_id,
            "session_id": session_uuid,
            "user_id": test_user.user_id,
        }
        
        message = await web_interface.handle_message(raw_data, broker_test_flow.flow_id)
        
        assert message is not None
        assert message.content == "Тестовое сообщение пользователя"
        assert session_uuid in message.session_id
        
        # Проверяем notification в storage
        container = get_agents_container()
        storage = container.storage
        
        pattern = f"web_notification:web:{test_user.user_id}:"
        keys = await storage.list_by_prefix(pattern, limit=10, force_global=True)
        
        assert len(keys) > 0, f"Уведомления не найдены: {pattern}"
        print(f"✅ Найдено уведомлений: {len(keys)}")
        
        # Очистка
        for key in keys:
            await storage.delete(key)
    
    @pytest.mark.asyncio
    async def test_agent_message_saved_as_notification(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
        unique_id,
    ):
        """AGENT_MESSAGE сохраняется как notification"""
        web_interface = WebInterface(platform_config={"enabled": True})
        session_id = f"web:{test_user.user_id}:{broker_test_flow.flow_id}:{unique_id('sess')}"
        
        message = Message(
            user_id=test_user.user_id,
            session_id=session_id,
            content="Ответ от агента",
            flow_id=broker_test_flow.flow_id,
            platform="web",
            metadata={"web_chat": True},
        )
        
        await web_interface.send_message(message)
        
        container = get_agents_container()
        storage = container.storage
        
        pattern = f"web_notification:web:{test_user.user_id}:"
        keys = await storage.list_by_prefix(pattern, limit=10, force_global=True)
        
        assert len(keys) > 0, "AGENT_MESSAGE notification не найден"
        print(f"✅ Уведомление агента сохранено")
        
        # Очистка
        for key in keys:
            await storage.delete(key)


class TestSessionIdSync:
    """Тесты синхронизации session_id"""
    
    @pytest.mark.asyncio
    async def test_client_uuid_preserved(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
    ):
        """UUID от клиента должен сохраняться в session_id"""
        web_interface = WebInterface(platform_config={"enabled": True})
        
        client_uuid = "abc12345-test-uuid-1234-567890abcdef"
        
        raw_data = {
            "message": "Тест с UUID",
            "agent_id": broker_test_flow.flow_id,
            "session_id": client_uuid,
            "user_id": test_user.user_id,
        }
        
        message = await web_interface.handle_message(raw_data, broker_test_flow.flow_id)
        
        assert message is not None
        assert client_uuid in message.session_id
        assert message.session_id.startswith("web:")
        
        print(f"✅ Client UUID: {client_uuid}")
        print(f"✅ Full session_id: {message.session_id}")
    
    @pytest.mark.asyncio
    async def test_full_session_id_accepted(
        self,
        migrated_db,
        taskiq_broker,
        broker_test_flow,
        test_context,
        test_user,
        unique_id,
    ):
        """Полный session_id принимается без изменений"""
        web_interface = WebInterface(platform_config={"enabled": True})
        
        full_session_id = f"web:{test_user.user_id}:{broker_test_flow.flow_id}:existing-uuid-123"
        
        raw_data = {
            "message": "Повторное сообщение",
            "agent_id": broker_test_flow.flow_id,
            "session_id": full_session_id,
            "user_id": test_user.user_id,
        }
        
        message = await web_interface.handle_message(raw_data, broker_test_flow.flow_id)
        
        assert message is not None
        assert message.session_id == full_session_id
        
        print(f"✅ Session ID сохранен: {message.session_id}")
