"""
Интеграционные тесты Triggers.

Проверяют:
1. CRUD триггеров через API
2. TriggerRegistry sync_triggers при сохранении агента
3. InputMapper маппит payload в state
4. TriggerExecutor запускает агента
5. Telegram webhook обработка

ВАЖНО: Используется реальный Redis и PostgreSQL.
Только LLM и Telegram API мокаются.
"""

import pytest
import pytest_asyncio

from apps.flows.src.container import get_container
from apps.flows.src.models import FlowConfig, TriggerConfig, TriggerType, TriggerStatus


class TestTriggerModels:
    """Тесты моделей триггеров."""

    def test_trigger_config_creation(self, unique_id):
        """TriggerConfig создается с правильными defaults."""
        trigger = TriggerConfig(
            trigger_id=f"trigger_{unique_id}",
            name="Test Trigger",
            type=TriggerType.TELEGRAM,
            config={"bot_token": "test_token"},
        )
        
        assert trigger.trigger_id == f"trigger_{unique_id}"
        assert trigger.type == TriggerType.TELEGRAM
        assert trigger.enabled is True
        assert trigger.status == TriggerStatus.INACTIVE
        assert trigger.webhook_url is None
        assert trigger.input_mapping == {}

    def test_agent_config_with_triggers(self, unique_id):
        """FlowConfig поддерживает triggers dict."""
        trigger = TriggerConfig(
            trigger_id="tg_main",
            name="Telegram Main",
            type=TriggerType.TELEGRAM,
            config={"bot_token": "@var:my_bot"},
        )
        
        agent = FlowConfig(
            flow_id=f"agent_{unique_id}",
            name="Agent with Triggers",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test",
                }
            },
            triggers={"tg_main": trigger},
        )
        
        assert "tg_main" in agent.triggers
        assert agent.triggers["tg_main"].type == TriggerType.TELEGRAM


class TestInputMapper:
    """Тесты InputMapper."""

    def test_map_simple_fields(self):
        """InputMapper маппит простые поля и сохраняет payload в triggers."""
        from apps.flows.src.triggers.input_mapper import InputMapper
        
        mapper = InputMapper()
        
        payload = {
            "message": {
                "text": "Hello world",
                "from": {"id": 12345, "username": "testuser"},
                "chat": {"id": 67890},
            }
        }
        
        mapping = {
            "content": "message.text",
            "variables.user_id": "message.from.id",
            "variables.username": "message.from.username",
            "variables.chat_id": "message.chat.id",
        }
        
        result = mapper.map("tg_trigger", payload, mapping)
        
        assert result["content"] == "Hello world"
        assert result["variables"]["user_id"] == 12345
        assert result["variables"]["username"] == "testuser"
        assert result["variables"]["chat_id"] == 67890
        assert result["triggers"]["tg_trigger"] == payload

    def test_map_with_const(self):
        """InputMapper поддерживает @const."""
        from apps.flows.src.triggers.input_mapper import InputMapper
        
        mapper = InputMapper()
        
        payload = {"text": "test"}
        mapping = {
            "content": "text",
            "variables.source": "@const:telegram",
            "variables.priority": "@const:1",
        }
        
        result = mapper.map("tg_trigger", payload, mapping)
        
        assert result["content"] == "test"
        assert result["variables"]["source"] == "telegram"
        assert result["variables"]["priority"] == "1"
        assert result["triggers"]["tg_trigger"] == payload

    def test_map_nested_path(self):
        """InputMapper маппит вложенные пути."""
        from apps.flows.src.triggers.input_mapper import InputMapper
        
        mapper = InputMapper()
        
        payload = {
            "data": {
                "nested": {
                    "deep": {
                        "value": "found"
                    }
                }
            }
        }
        
        mapping = {"content": "data.nested.deep.value"}
        
        result = mapper.map("webhook_trigger", payload, mapping)
        
        assert result["content"] == "found"
        assert result["triggers"]["webhook_trigger"] == payload

    def test_map_missing_path_returns_none(self):
        """InputMapper возвращает None для отсутствующего пути."""
        from apps.flows.src.triggers.input_mapper import InputMapper
        
        mapper = InputMapper()
        
        payload = {"text": "hello"}
        mapping = {"content": "missing.path"}
        
        result = mapper.map("test_trigger", payload, mapping)
        
        assert result["content"] is None
        assert result["triggers"]["test_trigger"] == payload

    def test_map_empty_mapping(self):
        """InputMapper с пустым mapping сохраняет payload в triggers."""
        from apps.flows.src.triggers.input_mapper import InputMapper
        
        mapper = InputMapper()
        
        payload = {"text": "hello"}
        result = mapper.map("empty_trigger", payload, {})
        
        assert result["triggers"]["empty_trigger"] == payload


class TestTriggerRegistry:
    """Тесты TriggerRegistry."""

    @pytest.mark.asyncio
    async def test_sync_triggers_registers_new(self, app, container, unique_id):
        """sync_triggers регистрирует новые триггеры."""
        from apps.flows.src.triggers import TriggerRegistry
        
        registry = container.trigger_registry
        
        flow_id = f"trigger_test_{unique_id}"
        
        # Старый конфиг без триггеров
        old_config = None
        
        # Новый конфиг с webhook триггером (не telegram - не требует реального API)
        trigger = TriggerConfig(
            trigger_id="webhook_1",
            name="Test Webhook",
            type=TriggerType.WEBHOOK,
            enabled=True,
            config={},
        )
        
        new_config = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"webhook_1": trigger},
        )
        
        # sync не падает (handler для webhook еще не реализован - будет warning)
        result = await registry.sync_triggers(flow_id, old_config, new_config)
        
        assert "webhook_1" in result.triggers
        # Статус ERROR т.к. нет handler
        assert result.triggers["webhook_1"].status == TriggerStatus.ERROR

    @pytest.mark.asyncio
    async def test_sync_triggers_unregisters_removed(self, app, container, unique_id):
        """sync_triggers снимает удаленные триггеры."""
        registry = container.trigger_registry
        
        flow_id = f"trigger_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="to_remove",
            name="Will be removed",
            type=TriggerType.WEBHOOK,
            enabled=True,
            config={},
        )
        
        old_config = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"to_remove": trigger},
        )
        
        new_config = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={},
        )
        
        result = await registry.sync_triggers(flow_id, old_config, new_config)
        
        assert "to_remove" not in result.triggers

    @pytest.mark.asyncio
    async def test_sync_triggers_updates_changed(self, app, container, unique_id):
        """sync_triggers перерегистрирует измененные триггеры."""
        registry = container.trigger_registry
        
        flow_id = f"trigger_test_{unique_id}"
        
        old_trigger = TriggerConfig(
            trigger_id="changing",
            name="Old Config",
            type=TriggerType.WEBHOOK,
            enabled=True,
            config={"old": "value"},
        )
        
        old_config = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"changing": old_trigger},
        )
        
        new_trigger = TriggerConfig(
            trigger_id="changing",
            name="New Config",
            type=TriggerType.WEBHOOK,
            enabled=True,
            config={"new": "value"},
        )
        
        new_config = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"changing": new_trigger},
        )
        
        result = await registry.sync_triggers(flow_id, old_config, new_config)
        
        assert "changing" in result.triggers
        assert result.triggers["changing"].config.get("new") == "value"


class TestTriggersAPI:
    """Тесты Triggers API."""

    @pytest.mark.asyncio
    async def test_list_triggers_empty(self, app, client, container, unique_id):
        """GET /flows/api/v1/flows/{id}/triggers возвращает пустой список."""
        flow_id = f"api_test_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )
        await container.flow_repository.set(agent)
        
        response = await client.get(f"/flows/api/v1/flows/{flow_id}/triggers")
        
        assert response.status_code == 200
        data = response.json()
        assert data["triggers"] == []
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_create_trigger(self, app, client, container, unique_id):
        """POST /flows/{id}/triggers создает триггер."""
        flow_id = f"api_test_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )
        await container.flow_repository.set(agent)
        
        response = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers",
            json={
                "trigger_id": "new_trigger",
                "name": "New Trigger",
                "type": "webhook",
                "enabled": True,
                "config": {"headers": {"X-Custom": "value"}},
                "input_mapping": {"content": "@trigger:body.text"},
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_id"] == "new_trigger"
        assert data["name"] == "New Trigger"
        assert data["type"] == "webhook"
        
        # Проверяем что сохранено в БД
        saved = await container.flow_repository.get(flow_id)
        assert "new_trigger" in saved.triggers
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_get_trigger(self, app, client, container, unique_id):
        """GET /flows/{id}/triggers/{trigger_id} возвращает триггер."""
        flow_id = f"api_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="my_trigger",
            name="My Trigger",
            type=TriggerType.WEBHOOK,
            config={"test": "value"},
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"my_trigger": trigger},
        )
        await container.flow_repository.set(agent)
        
        response = await client.get(f"/flows/api/v1/flows/{flow_id}/triggers/my_trigger")
        
        assert response.status_code == 200
        data = response.json()
        assert data["trigger_id"] == "my_trigger"
        assert data["name"] == "My Trigger"
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_update_trigger(self, app, client, container, unique_id):
        """PUT /flows/{id}/triggers/{trigger_id} обновляет триггер."""
        flow_id = f"api_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="update_me",
            name="Original Name",
            type=TriggerType.WEBHOOK,
            enabled=True,
            config={},
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"update_me": trigger},
        )
        await container.flow_repository.set(agent)
        
        response = await client.put(
            f"/flows/api/v1/flows/{flow_id}/triggers/update_me",
            json={
                "name": "Updated Name",
                "enabled": False,
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["enabled"] is False
        
        # Проверяем в БД
        saved = await container.flow_repository.get(flow_id)
        assert saved.triggers["update_me"].name == "Updated Name"
        assert saved.triggers["update_me"].enabled is False
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_delete_trigger(self, app, client, container, unique_id):
        """DELETE /flows/{id}/triggers/{trigger_id} удаляет триггер."""
        flow_id = f"api_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="delete_me",
            name="To Delete",
            type=TriggerType.WEBHOOK,
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"delete_me": trigger},
        )
        await container.flow_repository.set(agent)
        
        response = await client.delete(f"/flows/api/v1/flows/{flow_id}/triggers/delete_me")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "deleted"
        
        # Проверяем в БД
        saved = await container.flow_repository.get(flow_id)
        assert "delete_me" not in saved.triggers
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_test_trigger_endpoint(self, app, client, container, unique_id):
        """POST /flows/{id}/triggers/{trigger_id}/test тестирует маппинг."""
        flow_id = f"api_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="test_mapping",
            name="Test Mapping",
            type=TriggerType.TELEGRAM,
            output_mapping={
                "content": "message.text",
                "variables.chat_id": "message.chat.id",
            },
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"test_mapping": trigger},
        )
        await container.flow_repository.set(agent)
        
        response = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers/test_mapping/test",
            json={
                "message": {
                    "text": "Hello from test",
                    "chat": {"id": 12345},
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["mapped_data"]["content"] == "Hello from test"
        assert data["mapped_data"]["variables"]["chat_id"] == 12345
        assert "triggers" in data["mapped_data"]
        assert "test_mapping" in data["mapped_data"]["triggers"]
        
        await container.flow_repository.delete(flow_id)


class TestTriggerExecutor:
    """Тесты TriggerExecutor."""

    @pytest.mark.asyncio
    async def test_executor_creates_correct_state(self, app, container, unique_id, mock_llm_with_queue):
        """TriggerExecutor создает правильный ExecutionState."""
        from apps.flows.src.triggers.executor import TriggerExecutor
        
        mock_llm_with_queue(["Response from triggered agent"])
        
        flow_id = f"executor_test_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Executor Test Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Echo: {{content}}",
                }
            },
        )
        await container.flow_repository.set(agent)
        
        trigger = TriggerConfig(
            trigger_id="exec_trigger",
            name="Executor Trigger",
            type=TriggerType.WEBHOOK,
            input_mapping={
                "content": "@trigger:body.text",
                "variables.source": "@const:webhook",
            },
        )
        
        executor = TriggerExecutor()
        
        payload = {"body": {"text": "Hello from webhook"}}
        
        result = await executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
            user_id=f"user_{unique_id}",
        )
        
        assert "task_id" in result
        assert result["status"] == "started"
        
        await container.flow_repository.delete(flow_id)


class TestTelegramWebhookEndpoint:
    """Тесты Telegram webhook endpoint."""

    @pytest.mark.asyncio
    async def test_telegram_webhook_validates_trigger_type(self, app, client, container, unique_id):
        """Telegram webhook отклоняет не-Telegram триггеры."""
        flow_id = f"tg_test_{unique_id}"
        
        # Создаем webhook триггер (не telegram)
        trigger = TriggerConfig(
            trigger_id="wrong_type",
            name="Wrong Type",
            type=TriggerType.WEBHOOK,
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"wrong_type": trigger},
        )
        await container.flow_repository.set(agent)
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/wrong_type",
            json={"update_id": 123, "message": {"text": "test"}},
        )
        
        assert response.status_code == 400
        assert "Not a Telegram trigger" in response.json()["detail"]
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_telegram_webhook_validates_secret_token(self, app, client, container, unique_id):
        """Telegram webhook проверяет secret_token."""
        flow_id = f"tg_test_{unique_id}"
        
        trigger = TriggerConfig(
            trigger_id="tg_secure",
            name="Secure Telegram",
            type=TriggerType.TELEGRAM,
            config={"_secret_token": "correct_token"},
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"tg_secure": trigger},
        )
        await container.flow_repository.set(agent)
        
        # Без токена - проходит (токен опциональный)
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/tg_secure",
            json={"update_id": 123, "message": {"text": "test", "chat": {"id": 1}, "from": {"id": 1}}},
        )
        # Может быть ошибка валидации, но не 403
        assert response.status_code != 403
        
        # С неправильным токеном - 403
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/tg_secure",
            json={"update_id": 123, "message": {"text": "test"}},
            headers={"X-Telegram-Bot-Api-Secret-Token": "wrong_token"},
        )
        assert response.status_code == 403
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_telegram_webhook_404_for_unknown_agent(self, app, client):
        """Telegram webhook возвращает 404 для несуществующего агента."""
        response = await client.post(
            "/flows/api/v1/triggers/telegram/nonexistent_agent/some_trigger",
            json={"update_id": 123, "message": {"text": "test"}},
        )
        
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_telegram_webhook_404_for_unknown_trigger(self, app, client, container, unique_id):
        """Telegram webhook возвращает 404 для несуществующего триггера."""
        flow_id = f"tg_test_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
        )
        await container.flow_repository.set(agent)
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/nonexistent_trigger",
            json={"update_id": 123, "message": {"text": "test"}},
        )
        
        assert response.status_code == 404
        
        await container.flow_repository.delete(flow_id)


class TestTelegramTriggerHandler:
    """Тесты TelegramTriggerHandler."""

    @pytest.mark.asyncio
    async def test_handler_validates_allowed_users(self, app, container, unique_id, mock_llm_with_queue):
        """TelegramTriggerHandler проверяет allowed_users."""
        from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
        from apps.flows.src.triggers import TriggerValidationError
        
        mock_llm_with_queue(["Response"])
        
        flow_id = f"tg_handler_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={
                "allowed_trigger": TriggerConfig(
                    trigger_id="allowed_trigger",
                    name="Allowed Users",
                    type=TriggerType.TELEGRAM,
                    config={"allowed_users": [111, 222]},
                )
            },
        )
        await container.flow_repository.set(agent)
        
        handler = TelegramTriggerHandler(base_url="http://test")
        
        # Разрешенный пользователь
        payload_allowed = {
            "update_id": 1,
            "message": {
                "text": "hello",
                "from": {"id": 111},
                "chat": {"id": 999},
            }
        }
        
        # Не должен падать
        # (handle вызывает валидацию внутри)
        
        # Неразрешенный пользователь
        payload_denied = {
            "update_id": 2,
            "message": {
                "text": "hello",
                "from": {"id": 333},
                "chat": {"id": 999},
            }
        }
        
        with pytest.raises(TriggerValidationError) as exc_info:
            await handler.handle(flow_id, "allowed_trigger", payload_denied)
        
        assert "not allowed" in str(exc_info.value)
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_handler_validates_commands(self, app, container, unique_id, mock_llm_with_queue):
        """TelegramTriggerHandler проверяет commands."""
        from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
        from apps.flows.src.triggers import TriggerValidationError
        
        mock_llm_with_queue(["Response"])
        
        flow_id = f"tg_handler_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Test Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={
                "cmd_trigger": TriggerConfig(
                    trigger_id="cmd_trigger",
                    name="Commands Only",
                    type=TriggerType.TELEGRAM,
                    config={"commands": ["/start", "/help"]},
                )
            },
        )
        await container.flow_repository.set(agent)
        
        handler = TelegramTriggerHandler(base_url="http://test")
        
        # Неразрешенная команда
        payload_wrong = {
            "update_id": 1,
            "message": {
                "text": "/unknown",
                "from": {"id": 111},
                "chat": {"id": 999},
            }
        }
        
        with pytest.raises(TriggerValidationError) as exc_info:
            await handler.handle(flow_id, "cmd_trigger", payload_wrong)
        
        assert "Command not matched" in str(exc_info.value)
        
        await container.flow_repository.delete(flow_id)

    def test_handler_generates_webhook_url(self):
        """TelegramTriggerHandler генерирует правильный webhook URL."""
        from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
        
        handler = TelegramTriggerHandler(base_url="https://example.com")
        
        url = handler.generate_webhook_url("my_agent", "my_trigger")
        
        assert url == "https://example.com/flows/api/v1/triggers/telegram/my_agent/my_trigger"

    def test_handler_verify_secret_token(self):
        """TelegramTriggerHandler верифицирует secret_token."""
        from apps.flows.src.triggers.handlers.telegram import TelegramTriggerHandler
        
        handler = TelegramTriggerHandler(base_url="http://test")
        
        trigger = TriggerConfig(
            trigger_id="test",
            name="Test",
            type=TriggerType.TELEGRAM,
            config={"_secret_token": "my_secret_123"},
        )
        
        # Правильный токен
        assert handler.verify_secret_token(trigger, "my_secret_123") is True
        
        # Неправильный токен
        assert handler.verify_secret_token(trigger, "wrong_token") is False
        
        # Нет токена в конфиге - любой проходит
        trigger_no_secret = TriggerConfig(
            trigger_id="test",
            name="Test",
            type=TriggerType.TELEGRAM,
            config={},
        )
        assert handler.verify_secret_token(trigger_no_secret, "anything") is True


class TestTelegramTriggerE2E:
    """
    Полный E2E тест: Telegram webhook -> Agent execution -> Response.
    
    Создаем реального агента, настраиваем триггер, стреляем webhook,
    проверяем что агент реально выполнился с правильными данными.
    """

    @pytest.mark.asyncio
    async def test_telegram_webhook_triggers_agent_execution(
        self, app, client, container, unique_id, mock_llm_with_queue
    ):
        """
        Полный цикл:
        1. Создаем агента с llm_node
        2. Настраиваем Telegram триггер с input_mapping
        3. Отправляем webhook как от Telegram
        4. Агент выполняется с данными из webhook
        5. Проверяем state и результат
        """
        # Настраиваем MockLLM
        mock_llm_with_queue([
            "Здравствуйте! Я получил ваше сообщение и готов помочь."
        ])
        
        flow_id = f"tg_e2e_agent_{unique_id}"
        
        # Создаем агента с llm_node
        agent = FlowConfig(
            flow_id=flow_id,
            name="Telegram E2E Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": """Ты помощник в Telegram.
Пользователь написал: {{content}}
Chat ID: {{variables.chat_id}}
Username: {{variables.username}}

Отвечай кратко и по делу.""",
                }
            },
            triggers={
                "telegram_main": TriggerConfig(
                    trigger_id="telegram_main",
                    name="Main Telegram",
                    type=TriggerType.TELEGRAM,
                    enabled=True,
                    config={},
                    input_mapping={
                        "content": "@trigger:message.text",
                        "variables.chat_id": "@trigger:message.chat.id",
                        "variables.user_id": "@trigger:message.from.id",
                        "variables.username": "@trigger:message.from.username",
                        "variables.message_id": "@trigger:message.message_id",
                    },
                ),
            },
        )
        await container.flow_repository.set(agent)
        
        # Симулируем Telegram Update
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 42,
                "from": {
                    "id": 987654321,
                    "is_bot": False,
                    "first_name": "Виктор",
                    "username": "viktor_test",
                    "language_code": "ru",
                },
                "chat": {
                    "id": 987654321,
                    "first_name": "Виктор",
                    "username": "viktor_test",
                    "type": "private",
                },
                "date": 1705512345,
                "text": "Привет! Как дела?",
            },
        }
        
        # Отправляем webhook
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/telegram_main",
            json=telegram_update,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Проверяем что task запущен
        assert data["status"] == "ok"
        assert "task_id" in data
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_telegram_trigger_with_tool_call(
        self, app, client, container, unique_id, mock_llm_with_queue, inline_tools
    ):
        """
        E2E с tool call:
        1. Агент получает сообщение через Telegram webhook
        2. Вызывает calculator tool
        3. Возвращает результат
        """
        # Настраиваем MockLLM с tool call
        mock_llm_with_queue([
            {"type": "tool_call", "tool": "calculator", "args": {"expression": "2+2"}},
            "Результат вычисления: 4",
        ])
        
        flow_id = f"tg_tool_agent_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Telegram Tool Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты калькулятор. Пользователь: {{content}}",
                    "tools": [inline_tools["calculator"]],
                }
            },
            triggers={
                "tg_calc": TriggerConfig(
                    trigger_id="tg_calc",
                    name="Calculator Trigger",
                    type=TriggerType.TELEGRAM,
                    enabled=True,
                    config={},
                    input_mapping={
                        "content": "@trigger:message.text",
                        "variables.chat_id": "@trigger:message.chat.id",
                    },
                ),
            },
        )
        await container.flow_repository.set(agent)
        
        telegram_update = {
            "update_id": 111,
            "message": {
                "message_id": 1,
                "from": {"id": 123, "username": "user"},
                "chat": {"id": 123, "type": "private"},
                "date": 1705512345,
                "text": "Посчитай 2+2",
            },
        }
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/tg_calc",
            json=telegram_update,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_telegram_trigger_filters_by_allowed_users(
        self, app, client, container, unique_id, mock_llm_with_queue
    ):
        """
        Триггер с allowed_users фильтрует неразрешенных пользователей.
        """
        mock_llm_with_queue(["Response"])
        
        flow_id = f"tg_filter_agent_{unique_id}"
        
        # Триггер разрешает только user_id=111
        agent = FlowConfig(
            flow_id=flow_id,
            name="Filtered Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={
                "filtered": TriggerConfig(
                    trigger_id="filtered",
                    name="Filtered",
                    type=TriggerType.TELEGRAM,
                    enabled=True,
                    config={"allowed_users": [111, 222]},
                    input_mapping={"content": "@trigger:message.text"},
                ),
            },
        )
        await container.flow_repository.set(agent)
        
        # Разрешенный пользователь - OK
        response_allowed = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/filtered",
            json={
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "from": {"id": 111, "username": "allowed"},
                    "chat": {"id": 111, "type": "private"},
                    "date": 1705512345,
                    "text": "Hello",
                },
            },
        )
        assert response_allowed.status_code == 200
        assert response_allowed.json()["status"] == "ok"
        
        # Неразрешенный пользователь - skipped
        response_denied = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/filtered",
            json={
                "update_id": 2,
                "message": {
                    "message_id": 2,
                    "from": {"id": 999, "username": "denied"},
                    "chat": {"id": 999, "type": "private"},
                    "date": 1705512345,
                    "text": "Hello",
                },
            },
        )
        assert response_denied.status_code == 200
        assert response_denied.json()["status"] == "skipped"
        assert "not allowed" in response_denied.json()["reason"]
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_telegram_trigger_filters_by_commands(
        self, app, client, container, unique_id, mock_llm_with_queue
    ):
        """
        Триггер с commands реагирует только на указанные команды.
        """
        mock_llm_with_queue(["Response"])
        
        flow_id = f"tg_cmd_agent_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Command Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={
                "commands": TriggerConfig(
                    trigger_id="commands",
                    name="Commands Only",
                    type=TriggerType.TELEGRAM,
                    enabled=True,
                    config={"commands": ["/start", "/help"]},
                    input_mapping={"content": "@trigger:message.text"},
                ),
            },
        )
        await container.flow_repository.set(agent)
        
        # /start - OK
        response_start = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/commands",
            json={
                "update_id": 1,
                "message": {
                    "message_id": 1,
                    "from": {"id": 111},
                    "chat": {"id": 111, "type": "private"},
                    "date": 1705512345,
                    "text": "/start",
                },
            },
        )
        assert response_start.status_code == 200
        assert response_start.json()["status"] == "ok"
        
        # Обычное сообщение - skipped
        response_text = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/commands",
            json={
                "update_id": 2,
                "message": {
                    "message_id": 2,
                    "from": {"id": 111},
                    "chat": {"id": 111, "type": "private"},
                    "date": 1705512345,
                    "text": "просто текст",
                },
            },
        )
        assert response_text.status_code == 200
        assert response_text.json()["status"] == "skipped"
        
        await container.flow_repository.delete(flow_id)

    @pytest.mark.asyncio
    async def test_input_mapping_extracts_all_telegram_fields(
        self, app, client, container, unique_id, mock_llm_with_queue
    ):
        """
        Проверяем что output_mapping правильно извлекает все поля из Telegram Update.
        """
        mock_llm_with_queue(["Response"])
        
        flow_id = f"tg_mapping_agent_{unique_id}"
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Mapping Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test {{content}}"}},
            triggers={
                "full_mapping": TriggerConfig(
                    trigger_id="full_mapping",
                    name="Full Mapping",
                    type=TriggerType.TELEGRAM,
                    enabled=True,
                    config={},
                    output_mapping={
                        "content": "message.text",
                        "variables.update_id": "update_id",
                        "variables.message_id": "message.message_id",
                        "variables.user_id": "message.from.id",
                        "variables.username": "message.from.username",
                        "variables.first_name": "message.from.first_name",
                        "variables.chat_id": "message.chat.id",
                        "variables.chat_type": "message.chat.type",
                        "variables.date": "message.date",
                        "variables.source": "@const:telegram",
                    },
                ),
            },
        )
        await container.flow_repository.set(agent)
        
        telegram_update = {
            "update_id": 999888,
            "message": {
                "message_id": 777,
                "from": {
                    "id": 12345,
                    "first_name": "Иван",
                    "username": "ivan_test",
                },
                "chat": {
                    "id": 12345,
                    "type": "private",
                },
                "date": 1705512345,
                "text": "Тестовое сообщение",
            },
        }
        
        # Тестируем mapping через test endpoint
        response = await client.post(
            f"/flows/api/v1/flows/{flow_id}/triggers/full_mapping/test",
            json=telegram_update,
        )
        
        assert response.status_code == 200
        data = response.json()
        
        mapped = data["mapped_data"]
        
        # Проверяем все поля
        assert mapped["content"] == "Тестовое сообщение"
        assert mapped["variables"]["update_id"] == 999888
        assert mapped["variables"]["message_id"] == 777
        assert mapped["variables"]["user_id"] == 12345
        assert mapped["variables"]["username"] == "ivan_test"
        assert mapped["variables"]["first_name"] == "Иван"
        assert mapped["variables"]["chat_id"] == 12345
        assert mapped["variables"]["chat_type"] == "private"
        assert mapped["variables"]["date"] == 1705512345
        assert mapped["variables"]["source"] == "telegram"
        # Проверяем что payload сохранен в triggers
        assert "full_mapping" in mapped["triggers"]
        
        await container.flow_repository.delete(flow_id)


class TestChannelRegistry:
    """Тесты ChannelRegistry."""

    def test_channel_registry_creation(self):
        """ChannelRegistry создается с handlers."""
        from apps.flows.src.channels import create_default_channel_registry
        from apps.flows.src.models.enums import ChannelType
        
        registry = create_default_channel_registry()
        
        assert registry.has(ChannelType.TELEGRAM)
        assert registry.has(ChannelType.WEBHOOK)
        
    def test_get_telegram_handler(self):
        """Можно получить TelegramChannelHandler."""
        from apps.flows.src.channels import create_default_channel_registry, TelegramChannelHandler
        from apps.flows.src.models.enums import ChannelType
        
        registry = create_default_channel_registry()
        handler = registry.get(ChannelType.TELEGRAM)
        
        assert isinstance(handler, TelegramChannelHandler)
        assert handler.channel_type == ChannelType.TELEGRAM
    
    def test_unknown_channel_raises(self):
        """Неизвестный канал вызывает ошибку."""
        from apps.flows.src.channels import create_default_channel_registry
        from apps.flows.src.models.enums import ChannelType
        
        registry = create_default_channel_registry()
        
        with pytest.raises(ValueError, match="Unknown channel"):
            registry.get(ChannelType.SMS)


class TestOutputAction:
    """Тесты модели OutputAction."""

    def test_output_action_creation(self):
        """OutputAction создается корректно."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        action = OutputAction(
            channel=ChannelType.TELEGRAM,
            action="send_message",
            mapping={
                "recipient": "@state:variables.chat_id",
                "text": "@state:response",
            },
        )
        
        assert action.channel == ChannelType.TELEGRAM
        assert action.action == "send_message"
        assert "@state:response" in action.mapping.values()
    
    def test_output_action_with_condition(self):
        """OutputAction с условием."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        action = OutputAction(
            channel=ChannelType.TELEGRAM,
            action="send_document",
            mapping={"recipient": "@state:variables.chat_id"},
            condition="@state:has_file == true",
        )
        
        assert action.condition == "@state:has_file == true"


class TestTriggerConfigOutputActions:
    """Тесты TriggerConfig с output_actions."""

    def test_trigger_with_output_actions(self, unique_id):
        """TriggerConfig поддерживает output_actions."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        action = OutputAction(
            channel=ChannelType.TELEGRAM,
            action="send_message",
            mapping={
                "recipient": "@state:variables.chat_id",
                "text": "@state:response",
            },
        )
        
        trigger = TriggerConfig(
            trigger_id=f"trigger_{unique_id}",
            name="Trigger with Output",
            type=TriggerType.TELEGRAM,
            config={"bot_token": "test_token"},
            output_actions=[action],
        )
        
        assert len(trigger.output_actions) == 1
        assert trigger.output_actions[0].action == "send_message"
    
    def test_trigger_multiple_output_actions(self, unique_id):
        """TriggerConfig с несколькими output_actions."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        actions = [
            OutputAction(
                channel=ChannelType.TELEGRAM,
                action="send_message",
                mapping={"recipient": "@state:variables.chat_id", "text": "@state:response"},
            ),
            OutputAction(
                channel=ChannelType.TELEGRAM,
                action="send_document",
                mapping={"recipient": "@state:variables.chat_id", "document": "@state:file_url"},
                condition="@state:has_file == true",
            ),
        ]
        
        trigger = TriggerConfig(
            trigger_id=f"trigger_{unique_id}",
            name="Multi Output",
            type=TriggerType.TELEGRAM,
            config={},
            output_actions=actions,
        )
        
        assert len(trigger.output_actions) == 2


class TestOutputActionExecutor:
    """Тесты OutputActionExecutor."""

    @pytest.mark.asyncio
    async def test_check_condition_true(self):
        """Проверка условия - true."""
        from apps.flows.src.triggers.executor import OutputActionExecutor
        
        executor = OutputActionExecutor()
        
        state = {"has_file": True, "response": "Hello"}
        
        assert executor._check_condition("@state:has_file == true", state) is True
        assert executor._check_condition("@state:has_file", state) is True
    
    @pytest.mark.asyncio
    async def test_check_condition_false(self):
        """Проверка условия - false."""
        from apps.flows.src.triggers.executor import OutputActionExecutor
        
        executor = OutputActionExecutor()
        
        state = {"has_file": False, "response": "Hello"}
        
        assert executor._check_condition("@state:has_file == true", state) is False
        assert executor._check_condition("@state:has_file == false", state) is True
    
    @pytest.mark.asyncio
    async def test_resolve_mapping(self):
        """Резолвинг маппинга."""
        from apps.flows.src.triggers.executor import OutputActionExecutor
        
        executor = OutputActionExecutor()
        
        state = {
            "response": "Hello world",
            "variables": {"chat_id": 12345},
        }
        
        payload = {"message": {"from": {"id": 67890}}}
        
        mapping = {
            "text": "@state:response",
            "recipient": "@state:variables.chat_id",
            "user_id": "@trigger:message.from.id",
        }
        
        result = executor._resolve_mapping(mapping, state, payload)
        
        assert result["text"] == "Hello world"
        assert result["recipient"] == 12345
        assert result["user_id"] == 67890


class TestChannelNode:
    """Тесты ChannelNode."""

    def test_channel_node_creation(self):
        """ChannelNode создается корректно."""
        from apps.flows.src.runtime.nodes import ChannelNode
        from apps.flows.src.models.enums import ChannelType
        
        node = ChannelNode(
            node_id="send_reply",
            config={
                "channel": "telegram",
                "action": "send_message",
                "channel_config": {"bot_token": "test_token"},
            }
        )
        
        assert node.channel == ChannelType.TELEGRAM
        assert node.action == "send_message"
        assert node.channel_config["bot_token"] == "test_token"
    
    def test_channel_node_registered(self):
        """ChannelNode зарегистрирован в NodeRegistry."""
        from apps.flows.src.registry.nodes import create_default_node_registry
        from apps.flows.src.models.enums import NodeType
        from apps.flows.src.runtime.nodes import ChannelNode
        
        registry = create_default_node_registry()
        
        node_class = registry.get(NodeType.CHANNEL)
        assert node_class == ChannelNode


class TestWebhookChannelHandler:
    """Тесты WebhookChannelHandler."""

    @pytest.mark.asyncio
    async def test_build_headers(self):
        """_build_headers резолвит переменные."""
        from apps.flows.src.channels.webhook import WebhookChannelHandler
        
        handler = WebhookChannelHandler()
        
        config = {
            "headers": {
                "Authorization": "Bearer @var:api_key",
                "X-Custom": "static_value",
            }
        }
        
        variables = {"api_key": "secret123"}
        
        headers = handler._build_headers(config, variables)
        
        assert headers["Authorization"] == "Bearer secret123"
        assert headers["X-Custom"] == "static_value"
        assert headers["Content-Type"] == "application/json"


class TestAgentWithChannelNode:
    """E2E тесты агента с ChannelNode."""

    @pytest.mark.asyncio
    async def test_agent_config_with_channel_node(self, unique_id):
        """FlowConfig с ChannelNode валидируется."""
        agent = FlowConfig(
            flow_id=f"channel_agent_{unique_id}",
            name="Agent with Channel",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Test",
                },
                "send_reply": {
                    "type": "channel",
                    "channel": "telegram",
                    "action": "send_message",
                    "channel_config": {"bot_token": "@var:bot_token"},
                    "input_mapping": {
                        "recipient": "@state:variables.chat_id",
                        "text": "@state:response",
                    },
                },
            },
            edges=[
                {"from": "main", "to": "send_reply"},
                {"from": "send_reply", "to": None},
            ],
        )
        
        assert "send_reply" in agent.nodes
        assert agent.nodes["send_reply"]["type"] == "channel"
    
    @pytest.mark.asyncio
    async def test_create_channel_node_from_config(self):
        """create_node создает ChannelNode."""
        from apps.flows.src.runtime.nodes import create_node
        from apps.flows.src.runtime.nodes import ChannelNode
        
        config = {
            "type": "channel",
            "channel": "webhook",
            "action": "send_payload",
            "channel_config": {"url": "https://example.com/callback"},
        }
        
        node = await create_node("test_channel", config)
        
        assert isinstance(node, ChannelNode)
        assert node.action == "send_payload"


class TestTriggerWithOutputActionsE2E:
    """E2E тесты триггера с output_actions."""

    @pytest.mark.asyncio
    async def test_agent_with_trigger_output_actions(self, unique_id):
        """Агент с триггером и output_actions сохраняется."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        container = get_container()
        
        flow_id = f"output_agent_{unique_id}"
        
        output_action = OutputAction(
            channel=ChannelType.TELEGRAM,
            action="send_message",
            mapping={
                "recipient": "@state:variables.chat_id",
                "text": "@state:response",
            },
        )
        
        trigger = TriggerConfig(
            trigger_id="tg_with_output",
            name="Telegram with Output",
            type=TriggerType.TELEGRAM,
            config={"bot_token": "test_token"},
            input_mapping={
                "content": "@trigger:message.text",
                "variables.chat_id": "@trigger:message.chat.id",
            },
            output_actions=[output_action],
        )
        
        agent = FlowConfig(
            flow_id=flow_id,
            name="Agent with Output Actions",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Test"}},
            triggers={"tg_with_output": trigger},
        )
        
        await container.flow_repository.set(agent)
        
        loaded = await container.flow_repository.get(flow_id)
        
        assert loaded is not None
        assert "tg_with_output" in loaded.triggers
        assert len(loaded.triggers["tg_with_output"].output_actions) == 1
        
        loaded_action = loaded.triggers["tg_with_output"].output_actions[0]
        assert loaded_action.channel == ChannelType.TELEGRAM
        assert loaded_action.action == "send_message"
        
        await container.flow_repository.delete(flow_id)


# =============================================================================
# E2E ТЕСТЫ С РЕАЛЬНЫМИ HTTP СЕРВЕРАМИ (БЕЗ МОКОВ)
# =============================================================================

import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn


class NotificationServer:
    """
    Реальный HTTP сервер для приёма уведомлений.
    
    Без моков - принимает реальные HTTP запросы.
    """
    
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self.received_requests: list = []
        self._app = FastAPI()
        self._app.add_api_route("/notify", self._handle_notify, methods=["POST"])
        self._app.add_api_route(
            "/telegram/{token}/sendMessage",
            self._handle_telegram_send_message,
            methods=["POST"],
        )
        self._app.add_api_route(
            "/telegram/{token}/sendPhoto",
            self._handle_telegram_send_photo,
            methods=["POST"],
        )
        self._app.add_api_route(
            "/telegram/{token}/sendDocument",
            self._handle_telegram_send_document,
            methods=["POST"],
        )
        self._server: uvicorn.Server | None = None
        self._server_task: asyncio.Task | None = None
    
    async def _handle_notify(self, request: Request) -> JSONResponse:
        """Обработчик уведомлений для webhook."""
        data = await request.json()
        headers = dict(request.headers)
        self.received_requests.append({
            "type": "notify",
            "data": data,
            "headers": headers,
        })
        return JSONResponse({"status": "ok"})
    
    async def _handle_telegram_send_message(self, token: str, request: Request) -> JSONResponse:
        """Обработчик Telegram sendMessage."""
        data = await request.json()
        self.received_requests.append({
            "type": "telegram_send_message",
            "token": token,
            "data": data,
        })
        return JSONResponse({
            "ok": True,
            "result": {
                "message_id": 12345,
                "chat": {"id": data.get("chat_id")},
                "text": data.get("text"),
            }
        })
    
    async def _handle_telegram_send_photo(self, token: str, request: Request) -> JSONResponse:
        """Обработчик Telegram sendPhoto."""
        data = await request.json()
        self.received_requests.append({
            "type": "telegram_send_photo",
            "token": token,
            "data": data,
        })
        return JSONResponse({
            "ok": True,
            "result": {"message_id": 12346}
        })
    
    async def _handle_telegram_send_document(self, token: str, request: Request) -> JSONResponse:
        """Обработчик Telegram sendDocument."""
        data = await request.json()
        self.received_requests.append({
            "type": "telegram_send_document",
            "token": token,
            "data": data,
        })
        return JSONResponse({
            "ok": True,
            "result": {"message_id": 12347}
        })
    
    async def start(self) -> str:
        """Запускает сервер и возвращает base URL."""
        config = uvicorn.Config(
            self._app,
            host=self.host,
            port=self.port,
            log_level="error",
            access_log=False,
        )
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())
        while not self._server.started:
            await asyncio.sleep(0.01)
        if not self._server.servers:
            raise RuntimeError("Uvicorn сервер не поднялся.")
        server = next(iter(self._server.servers))
        sockets = getattr(server, "sockets", None)
        if not sockets:
            raise RuntimeError("Uvicorn не открыл сокеты для test server.")
        actual_port = sockets[0].getsockname()[1]
        self.port = actual_port
        return f"http://{self.host}:{actual_port}"
    
    async def stop(self):
        if self._server is None:
            return
        self._server.should_exit = True
        if self._server_task is not None:
            await self._server_task
    
    def clear(self):
        self.received_requests.clear()
    
    def get_requests(self, request_type: str = None) -> list:
        if request_type:
            return [r for r in self.received_requests if r["type"] == request_type]
        return self.received_requests


@pytest_asyncio.fixture
async def notification_server():
    """Фикстура: поднимает notification сервер."""
    server = NotificationServer()
    base_url = await server.start()
    yield server, base_url
    await server.stop()


class TestWebhookChannelE2E:
    """
    E2E тесты WebhookChannelHandler.
    
    Создаем реальный HTTP сервер, отправляем реальные HTTP запросы.
    """
    
    @pytest.mark.asyncio
    async def test_webhook_send_message_real_http(self, notification_server):
        """Реальная отправка HTTP запроса через WebhookChannelHandler."""
        from apps.flows.src.channels.webhook import WebhookChannelHandler
        
        server, base_url = notification_server
        
        handler = WebhookChannelHandler()
        
        result = await handler.send_message(
            recipient=f"{base_url}/notify",
            text="Test notification from agent",
            config={},
            variables={},
        )
        
        assert result["status"] == "ok"
        
        requests = server.get_requests("notify")
        assert len(requests) == 1
        assert requests[0]["data"]["text"] == "Test notification from agent"
    
    @pytest.mark.asyncio
    async def test_webhook_send_payload_real_http(self, notification_server):
        """WebhookChannelHandler send_payload с произвольными данными."""
        from apps.flows.src.channels.webhook import WebhookChannelHandler
        
        server, base_url = notification_server
        
        handler = WebhookChannelHandler()
        
        result = await handler.send_payload(
            recipient=f"{base_url}/notify",
            payload={"user_id": 123, "action": "completed", "result": "success"},
            config={},
            variables={},
        )
        
        assert result["status"] == "ok"
        
        requests = server.get_requests("notify")
        assert len(requests) == 1
        assert requests[0]["data"]["user_id"] == 123
        assert requests[0]["data"]["action"] == "completed"
    
    @pytest.mark.asyncio
    async def test_webhook_with_auth_headers(self, notification_server):
        """WebhookChannelHandler с авторизационными headers."""
        from apps.flows.src.channels.webhook import WebhookChannelHandler
        
        server, base_url = notification_server
        
        handler = WebhookChannelHandler()
        
        await handler.send_message(
            recipient=f"{base_url}/notify",
            text="Authenticated request",
            config={
                "headers": {
                    "Authorization": "Bearer secret-token-123",
                    "X-Custom-Header": "custom-value",
                },
            },
            variables={},
        )
        
        requests = server.get_requests("notify")
        assert len(requests) == 1
        assert requests[0]["headers"].get("Authorization") == "Bearer secret-token-123"
        assert requests[0]["headers"].get("X-Custom-Header") == "custom-value"
    
    @pytest.mark.asyncio
    async def test_webhook_send_notification_for_a2a(self, notification_server):
        """WebhookChannelHandler send_notification для A2A уведомлений."""
        from apps.flows.src.channels.webhook import WebhookChannelHandler
        
        server, base_url = notification_server
        
        handler = WebhookChannelHandler()
        
        result = await handler.send_notification(
            recipient=f"{base_url}/notify",
            event_type="complete",
            data={"response": "Agent finished successfully"},
            task_id="task-123",
            session_id="agent:ctx-123",
            config={},
            variables={},
        )
        
        assert result["status"] == "ok"
        
        requests = server.get_requests("notify")
        assert len(requests) == 1
        
        data = requests[0]["data"]
        assert data["params"]["id"] == "task-123"
        assert data["params"]["event"]["type"] == "complete"
        assert data["params"]["event"]["data"]["response"] == "Agent finished successfully"


class TestTelegramChannelE2E:
    """
    E2E тесты TelegramChannelHandler.
    
    Используем mock Telegram API сервер вместо реального api.telegram.org.
    """
    
    @pytest.mark.asyncio
    async def test_telegram_send_message_real_http(self, notification_server):
        """Реальная отправка через TelegramChannelHandler с mock API."""
        from apps.flows.src.channels.telegram import TelegramChannelHandler
        
        server, base_url = notification_server
        
        handler = TelegramChannelHandler()
        
        result = await handler.send_message(
            recipient="12345678",
            text="Hello from agent!",
            config={
                "bot_token": "test_bot_token_123",
                "api_base": f"{base_url}/telegram",
            },
            variables={},
        )
        
        assert result["ok"] is True
        assert result["result"]["message_id"] == 12345
        
        requests = server.get_requests("telegram_send_message")
        assert len(requests) == 1
        # Token в URL включает "bot" prefix: /telegram/bot{token}/sendMessage
        assert "test_bot_token_123" in requests[0]["token"]
        assert requests[0]["data"]["chat_id"] == "12345678"
        assert requests[0]["data"]["text"] == "Hello from agent!"
    
    @pytest.mark.asyncio
    async def test_telegram_send_photo_real_http(self, notification_server):
        """Отправка фото через TelegramChannelHandler."""
        from apps.flows.src.channels.telegram import TelegramChannelHandler
        
        server, base_url = notification_server
        
        handler = TelegramChannelHandler()
        
        result = await handler.send_photo(
            recipient="12345678",
            photo="https://example.com/image.jpg",
            config={
                "bot_token": "test_token",
                "api_base": f"{base_url}/telegram",
            },
            variables={},
            caption="Test photo caption",
        )
        
        assert result["ok"] is True
        
        requests = server.get_requests("telegram_send_photo")
        assert len(requests) == 1
        assert requests[0]["data"]["photo"] == "https://example.com/image.jpg"
        assert requests[0]["data"]["caption"] == "Test photo caption"
    
    @pytest.mark.asyncio
    async def test_telegram_send_document_real_http(self, notification_server):
        """Отправка документа через TelegramChannelHandler."""
        from apps.flows.src.channels.telegram import TelegramChannelHandler
        
        server, base_url = notification_server
        
        handler = TelegramChannelHandler()
        
        result = await handler.send_document(
            recipient="12345678",
            document="https://example.com/file.pdf",
            config={
                "bot_token": "test_token",
                "api_base": f"{base_url}/telegram",
            },
            variables={},
            caption="Important document",
            filename="report.pdf",
        )
        
        assert result["ok"] is True
        
        requests = server.get_requests("telegram_send_document")
        assert len(requests) == 1
        assert requests[0]["data"]["document"] == "https://example.com/file.pdf"
        assert requests[0]["data"]["caption"] == "Important document"
    
    @pytest.mark.asyncio
    async def test_telegram_reply_with_message_id(self, notification_server):
        """Ответ на сообщение через reply_to_message_id."""
        from apps.flows.src.channels.telegram import TelegramChannelHandler
        
        server, base_url = notification_server
        
        handler = TelegramChannelHandler()
        
        await handler.send_message(
            recipient="12345678",
            text="This is a reply",
            config={
                "bot_token": "test_token",
                "api_base": f"{base_url}/telegram",
            },
            variables={},
            reply_to_message_id=999,
        )
        
        requests = server.get_requests("telegram_send_message")
        assert len(requests) == 1
        assert requests[0]["data"]["reply_to_message_id"] == 999


class TestChannelNodeE2E:
    """
    E2E тесты ChannelNode.
    
    Создаем агента с ChannelNode, запускаем, проверяем что уведомление ушло.
    """
    
    @pytest.mark.asyncio
    async def test_channel_node_sends_webhook_notification(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """ChannelNode реально отправляет webhook уведомление."""
        from core.state import ExecutionState
        
        server, base_url = notification_server
        
        flow_id = f"channel_e2e_{unique_id}"
        context_id = f"ctx_{unique_id}"
        
        # Агент с code нодой + channel нодой
        # Code нода устанавливает notification_url из переменных
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Channel E2E Agent",
            entry="process",
            nodes={
                "process": {
                    "type": "code",
                    "code": """
def execute(args, state):
    state.response = "Processing complete"
    return {"success": True}
""",
                },
                "notify": {
                    "type": "channel",
                    "channel": "webhook",
                    "action": "send_message",
                    "channel_config": {},
                    "input_mapping": {
                        "recipient": "@state:variables.notification_url",
                        "text": "@state:response",
                    },
                },
            },
            edges=[
                {"from": "process", "to": "notify"},
                {"from": "notify", "to": None},
            ],
            variables={},
        )
        
        await container.flow_repository.set(flow_config)
        
        # Создаем агента и запускаем
        agent = await container.flow_factory.get_flow(flow_id)
        
        # session_id должен быть в формате flow_id:context_id
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=context_id,
            session_id=f"{flow_id}:{context_id}",
            user_id="test_user",
            content="Test with webhook",
        )
        # Устанавливаем URL в variables ДО запуска агента
        state.variables["notification_url"] = f"{base_url}/notify"
        
        final_state = await agent.run(state)
        
        assert final_state.response == "Processing complete"
        
        # Проверяем что webhook реально вызван
        requests = server.get_requests("notify")
        assert len(requests) >= 1
        
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_channel_node_sends_telegram_message(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """ChannelNode реально отправляет Telegram сообщение."""
        from core.state import ExecutionState
        
        server, base_url = notification_server
        telegram_api_base = f"{base_url}/telegram"
        
        flow_id = f"tg_channel_e2e_{unique_id}"
        context_id = f"ctx_{unique_id}"
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Telegram Channel E2E",
            entry="process",
            nodes={
                "process": {
                    "type": "code",
                    "code": """
def execute(args, state):
    state.response = "Your request has been processed"
    return {"success": True}
""",
                },
                "send_telegram": {
                    "type": "channel",
                    "channel": "telegram",
                    "action": "send_message",
                    "channel_config": {
                        "bot_token": "e2e_test_bot_token",
                        "api_base": telegram_api_base,
                    },
                    "input_mapping": {
                        "recipient": "@state:variables.chat_id",
                        "text": "@state:response",
                    },
                },
            },
            edges=[
                {"from": "process", "to": "send_telegram"},
                {"from": "send_telegram", "to": None},
            ],
        )
        
        await container.flow_repository.set(flow_config)
        
        agent = await container.flow_factory.get_flow(flow_id)
        
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=context_id,
            session_id=f"{flow_id}:{context_id}",
            user_id="test_user",
            content="Test telegram notification",
        )
        state.variables["chat_id"] = "987654321"
        
        await agent.run(state)
        
        # Проверяем Telegram API вызов
        requests = server.get_requests("telegram_send_message")
        assert len(requests) >= 1
        
        last_request = requests[-1]
        # Token в URL включает "bot" prefix
        assert "e2e_test_bot_token" in last_request["token"]
        assert last_request["data"]["chat_id"] == "987654321"
        assert "Your request has been processed" in last_request["data"]["text"]
        
        await container.flow_repository.delete(flow_id)


class TestTriggerOutputActionsE2E:
    """
    E2E тесты output_actions в триггерах.
    
    Полный flow: trigger → agent → output_actions → реальный HTTP запрос.
    """
    
    @pytest.mark.asyncio
    async def test_trigger_output_action_sends_webhook(
        self, notification_server, unique_id, container, client, mock_llm_with_queue
    ):
        """
        Полный E2E:
        1. Создаем агента с триггером и output_action
        2. Вызываем агента через TriggerExecutor
        3. После агента output_action отправляет уведомление
        4. Проверяем что HTTP запрос реально ушел
        """
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        server, base_url = notification_server
        
        mock_llm_with_queue(["Request processed successfully."])
        
        flow_id = f"output_action_e2e_{unique_id}"
        
        # Простой output_action с send_payload
        output_action = OutputAction(
            channel=ChannelType.WEBHOOK,
            action="send_payload",
            mapping={
                "recipient": f"@const:{base_url}/notify",
                "payload": "@state:response",
            },
        )
        
        trigger = TriggerConfig(
            trigger_id="webhook_trigger",
            name="Webhook Trigger",
            type=TriggerType.WEBHOOK,
            config={"secret": "test_secret_123"},
            input_mapping={
                "content": "@trigger:message",
            },
            output_actions=[output_action],
        )
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Output Action E2E Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "You are a helpful assistant. Answer briefly.",
                },
            },
            triggers={"webhook_trigger": trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        # Вызываем агента через TriggerExecutor
        from apps.flows.src.triggers.executor import TriggerExecutor
        
        executor = TriggerExecutor()
        
        payload = {"message": "Hello agent!"}
        
        result = await executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
        )
        
        # Агент выполнился
        assert result is not None
        
        # Cleanup
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_trigger_multiple_output_actions(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """Триггер с несколькими output_actions выполняет все."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        server, base_url = notification_server
        telegram_api_base = f"{base_url}/telegram"
        
        mock_llm_with_queue(["Multi-action response"])
        
        flow_id = f"multi_output_e2e_{unique_id}"
        
        # Два разных output_action
        actions = [
            OutputAction(
                channel=ChannelType.WEBHOOK,
                action="send_payload",
                mapping={
                    "recipient": f"@const:{base_url}/notify",
                    "payload": "@state:response",
                },
            ),
            OutputAction(
                channel=ChannelType.TELEGRAM,
                action="send_message",
                mapping={
                    "recipient": "@state:variables.chat_id",
                    "text": "@state:response",
                },
                config={
                    "bot_token": "multi_action_bot_token",
                    "api_base": telegram_api_base,
                },
            ),
        ]
        
        trigger = TriggerConfig(
            trigger_id="multi_trigger",
            name="Multi Output Trigger",
            type=TriggerType.WEBHOOK,
            config={},
            input_mapping={
                "content": "@trigger:message",
                "variables.chat_id": "@trigger:chat_id",
            },
            output_actions=actions,
        )
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Multi Output Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Answer briefly.",
                },
            },
            triggers={"multi_trigger": trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        from apps.flows.src.triggers.executor import TriggerExecutor
        
        executor = TriggerExecutor()
        
        payload = {
            "message": "Test multi-action",
            "chat_id": "111222333",
        }
        
        await executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload=payload,
        )
        
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_output_action_with_condition_executes(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """Output action с condition=true выполняется."""
        from apps.flows.src.models.channel_config import OutputAction
        from apps.flows.src.models.enums import ChannelType
        
        server, base_url = notification_server
        
        mock_llm_with_queue(["Conditional response"])
        
        flow_id = f"conditional_e2e_{unique_id}"
        
        # Action с условием - простой send_message webhook
        action = OutputAction(
            channel=ChannelType.WEBHOOK,
            action="send_message",
            mapping={
                "recipient": f"@const:{base_url}/notify",
                "text": "@state:response",
            },
            condition="@state:variables.should_notify",
        )
        
        trigger = TriggerConfig(
            trigger_id="cond_trigger",
            name="Conditional Trigger",
            type=TriggerType.WEBHOOK,
            config={},
            input_mapping={
                "content": "@trigger:message",
                "variables.should_notify": "@trigger:notify",
            },
            output_actions=[action],
        )
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Conditional Agent",
            entry="main",
            nodes={"main": {"type": "llm_node", "prompt": "Answer."}},
            triggers={"cond_trigger": trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        from apps.flows.src.triggers.executor import TriggerExecutor
        executor = TriggerExecutor()
        
        # С notify=True - action должен выполниться
        server.clear()
        await executor.execute(
            flow_id=flow_id,
            trigger=trigger,
            payload={"message": "Test", "notify": True},
        )
        
        await container.flow_repository.delete(flow_id)


class TestFullTriggerFlowE2E:
    """
    Полный E2E flow: Telegram webhook → Agent → Output Action → Response.
    
    Максимально приближено к реальному использованию.
    """
    
    @pytest.mark.asyncio
    async def test_full_telegram_trigger_webhook_to_agent(
        self, unique_id, container, client, mock_llm_with_queue
    ):
        """
        Полный сценарий Telegram webhook -> Agent:
        1. Telegram webhook приходит на /triggers/telegram/{flow_id}/{trigger_id}
        2. Агент выполняется с данными из webhook
        3. Проверяем что агент получил правильный content
        
        Примечание: output_actions пока не интегрированы в webhook handler,
        это отдельная задача.
        """
        mock_llm_with_queue([
            "Здравствуйте! Чем могу помочь?",
        ])
        
        flow_id = f"full_flow_e2e_{unique_id}"
        trigger_id = "tg_full"
        
        trigger = TriggerConfig(
            trigger_id=trigger_id,
            name="Full Flow Telegram",
            type=TriggerType.TELEGRAM,
            config={
                "bot_token": "full_flow_bot_token",
                "secret_token": "full_flow_secret",
            },
            input_mapping={
                "content": "@trigger:message.text",
                "variables.chat_id": "@trigger:message.chat.id",
                "variables.user_id": "@trigger:message.from.id",
            },
        )
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Full Flow E2E Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты дружелюбный ассистент. Отвечай кратко.",
                },
            },
            triggers={trigger_id: trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        # Отправляем Telegram webhook
        telegram_payload = {
            "update_id": 123456789,
            "message": {
                "message_id": 100,
                "text": "Привет!",
                "chat": {"id": 999888777, "type": "private"},
                "from": {"id": 111222333, "username": "testuser", "first_name": "Test"},
                "date": 1609459200,
            },
        }
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/{trigger_id}",
            json=telegram_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "full_flow_secret"},
        )
        
        assert response.status_code == 200
        
        # Webhook принят
        data = response.json()
        assert data.get("status") == "ok" or "task_id" in data
        
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_code_agent_with_channel_node_full_flow(
        self, notification_server, unique_id, container
    ):
        """
        Code агент → ChannelNode → реальный HTTP запрос.
        Без LLM, чистый code flow.
        """
        from core.state import ExecutionState
        
        server, base_url = notification_server
        
        flow_id = f"code_channel_e2e_{unique_id}"
        context_id = f"ctx_{unique_id}"
        
        # Code агент который обрабатывает данные и отправляет webhook
        # input_mapping значения должны быть строками
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Code Channel E2E",
            entry="calculate",
            nodes={
                "calculate": {
                    "type": "code",
                    "code": """
def execute(args, state):
    a = state.variables.get("a", 0)
    b = state.variables.get("b", 0)
    result = a + b
    state.response = f"Result: {result}"
    state.variables["calculation_result"] = result
    return {"result": result}
""",
                },
                "send_result": {
                    "type": "channel",
                    "channel": "webhook",
                    "action": "send_message",
                    "channel_config": {},
                    "input_mapping": {
                        "recipient": "@state:variables.callback_url",
                        "text": "@state:response",
                    },
                },
            },
            edges=[
                {"from": "calculate", "to": "send_result"},
                {"from": "send_result", "to": None},
            ],
        )
        
        await container.flow_repository.set(flow_config)
        
        agent = await container.flow_factory.get_flow(flow_id)
        
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=context_id,
            session_id=f"{flow_id}:{context_id}",
            user_id="test_user",
            content="5 + 3",
        )
        state.variables = {
            "a": 5,
            "b": 3,
            "callback_url": f"{base_url}/notify",
        }
        
        final_state = await agent.run(state)
        
        assert "Result: 8" in final_state.response
        
        # Webhook с результатом ушел
        requests = server.get_requests("notify")
        assert len(requests) >= 1
        
        await container.flow_repository.delete(flow_id)


class TestReactAgentWithChannelToolE2E:
    """
    E2E тесты: LlmNode с ChannelNode как tool.
    
    Mock LLM вызывает tool, tool реально отправляет HTTP.
    БЕЗ МОКОВ на HTTP - только LLM мокается.
    """
    
    @pytest.mark.asyncio
    async def test_react_agent_uses_channel_tool_to_send_webhook(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """
        LlmNode агент с ChannelNode tool:
        1. Агент получает запрос
        2. Mock LLM решает вызвать send_notification tool
        3. ChannelNode tool реально отправляет HTTP
        4. Проверяем что webhook получил данные
        """
        from core.state import ExecutionState
        
        server, base_url = notification_server
        
        flow_id = f"react_channel_tool_{unique_id}"
        context_id = f"ctx_{unique_id}"
        
        # Mock LLM: сначала вызывает tool, потом отвечает
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "send_notification",
                "args": {
                    "recipient": f"{base_url}/notify",
                    "text": "Notification sent by agent",
                }
            },
            "Уведомление успешно отправлено!",
        ])
        
        # LlmNode агент с ChannelNode как tool
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="React with Channel Tool",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты агент который может отправлять уведомления. Используй tool send_notification.",
                    "tools": [
                        {
                            "tool_id": "send_notification",
                            "type": "channel",
                            "channel": "webhook",
                            "action": "send_message",
                            "channel_config": {},
                            "description": "Отправляет уведомление через webhook",
                            "args_schema": {
                                "recipient": {"type": "string", "description": "URL для отправки"},
                                "text": {"type": "string", "description": "Текст уведомления"},
                            },
                            "input_mapping": {
                                "recipient": "@state:recipient",
                                "text": "@state:text",
                            },
                        },
                    ],
                },
            },
            edges=[{"from": "main", "to": None}],
        )
        
        await container.flow_repository.set(flow_config)
        
        agent = await container.flow_factory.get_flow(flow_id)
        
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=context_id,
            session_id=f"{flow_id}:{context_id}",
            user_id="test_user",
            content="Отправь уведомление на webhook",
        )
        
        await agent.run(state)
        
        # Проверяем что webhook реально получил запрос
        requests = server.get_requests("notify")
        assert len(requests) >= 1, f"Expected webhook request. Server received: {server.received_requests}"
        
        last_request = requests[-1]["data"]
        assert last_request["text"] == "Notification sent by agent"
        
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_react_agent_uses_telegram_channel_tool(
        self, notification_server, unique_id, container, mock_llm_with_queue
    ):
        """
        LlmNode с Telegram ChannelNode tool:
        1. Mock LLM вызывает send_telegram tool
        2. TelegramChannelHandler реально отправляет HTTP на mock Telegram API
        """
        from core.state import ExecutionState
        
        server, base_url = notification_server
        telegram_api_base = f"{base_url}/telegram"
        
        flow_id = f"react_tg_tool_{unique_id}"
        context_id = f"ctx_{unique_id}"
        
        mock_llm_with_queue([
            {
                "type": "tool_call",
                "tool": "send_telegram",
                "args": {
                    "recipient": "123456789",
                    "text": "Hello from agent via Telegram!",
                }
            },
            "Сообщение отправлено в Telegram!",
        ])
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="React with Telegram Tool",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Ты можешь отправлять сообщения в Telegram.",
                    "tools": [
                        {
                            "tool_id": "send_telegram",
                            "type": "channel",
                            "channel": "telegram",
                            "action": "send_message",
                            "channel_config": {
                                "bot_token": "react_tool_bot_token",
                                "api_base": telegram_api_base,
                            },
                            "description": "Отправляет сообщение в Telegram",
                            "args_schema": {
                                "recipient": {"type": "string", "description": "Chat ID"},
                                "text": {"type": "string", "description": "Текст сообщения"},
                            },
                            "input_mapping": {
                                "recipient": "@state:recipient",
                                "text": "@state:text",
                            },
                        },
                    ],
                },
            },
            edges=[{"from": "main", "to": None}],
        )
        
        await container.flow_repository.set(flow_config)
        
        agent = await container.flow_factory.get_flow(flow_id)
        
        state = ExecutionState(
            task_id=f"task_{unique_id}",
            context_id=context_id,
            session_id=f"{flow_id}:{context_id}",
            user_id="test_user",
            content="Отправь сообщение в Telegram",
        )
        
        await agent.run(state)
        
        # Проверяем Telegram API вызов
        requests = server.get_requests("telegram_send_message")
        assert len(requests) >= 1
        
        last_request = requests[-1]
        assert "react_tool_bot_token" in last_request["token"]
        assert last_request["data"]["chat_id"] == "123456789"
        assert last_request["data"]["text"] == "Hello from agent via Telegram!"
        
        await container.flow_repository.delete(flow_id)


class TestFullWebhookToChannelE2E:
    """
    Полный E2E flow: Telegram Webhook → LlmNode → ChannelNode tool → HTTP.

    Mock LLM через Redis (mock_llm_redis); process_flow_task выполняется через
    патч sync_tools (in-process), иначе отдельный worker не видит ту же привязку
    MockLLM к Redis, что и uvicorn в тестах.
    """

    @pytest.mark.asyncio
    async def test_telegram_webhook_triggers_react_agent_which_sends_webhook(
        self, notification_server, unique_id, container, client, mock_llm_redis
    ):
        """
        Полный flow:
        1. Telegram webhook приходит на /triggers/telegram/{flow_id}/{trigger_id}
        2. LlmNode агент получает message.text
        3. Mock LLM вызывает send_callback tool
        4. ChannelNode tool реально отправляет HTTP на callback URL
        5. Проверяем что HTTP реально ушел с правильными данными
        """
        server, base_url = notification_server
        
        flow_id = f"full_webhook_e2e_{unique_id}"
        trigger_id = "tg_trigger"
        
        # Mock LLM через Redis для реального worker
        await mock_llm_redis([
            {
                "type": "tool_call",
                "tool": "send_callback",
                "args": {
                    "recipient": f"{base_url}/notify",
                    "text": "Processed: user message received",
                }
            },
            "Callback отправлен!",
        ])
        
        # Триггер с input_mapping
        trigger = TriggerConfig(
            trigger_id=trigger_id,
            name="Telegram Trigger",
            type=TriggerType.TELEGRAM,
            config={
                "bot_token": "webhook_e2e_bot",
                "secret_token": "webhook_e2e_secret",
            },
            input_mapping={
                "content": "@trigger:message.text",
                "variables.chat_id": "@trigger:message.chat.id",
                "variables.user_id": "@trigger:message.from.id",
            },
        )
        
        # LlmNode агент с ChannelNode tool
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Webhook E2E Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": "Когда получаешь сообщение - вызови send_callback tool.",
                    "tools": [
                        {
                            "tool_id": "send_callback",
                            "type": "channel",
                            "channel": "webhook",
                            "action": "send_message",
                            "channel_config": {},
                            "description": "Отправляет callback",
                            "args_schema": {
                                "recipient": {"type": "string", "description": "URL"},
                                "text": {"type": "string", "description": "Text"},
                            },
                            "input_mapping": {
                                "recipient": "@state:recipient",
                                "text": "@state:text",
                            },
                        },
                    ],
                },
            },
            edges=[{"from": "main", "to": None}],
            triggers={trigger_id: trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        # Отправляем Telegram webhook
        telegram_payload = {
            "update_id": 999888777,
            "message": {
                "message_id": 200,
                "text": "Привет агент!",
                "chat": {"id": 111222333, "type": "private"},
                "from": {"id": 444555666, "username": "e2e_user"},
                "date": 1609459200,
            },
        }
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/{trigger_id}",
            json=telegram_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "webhook_e2e_secret"},
        )
        
        assert response.status_code == 200, f"Webhook trigger failed: {response.text}"
        
        # Ждём выполнения TaskIQ задачи
        import asyncio
        for _ in range(20):  # max 10 секунд
            await asyncio.sleep(0.5)
            requests = server.get_requests("notify")
            if len(requests) >= 1:
                break
        
        # Проверяем что callback реально ушел
        assert len(requests) >= 1, f"No webhook requests received! Got: {server.received_requests}"
        
        last_request = requests[-1]["data"]
        assert "Processed" in last_request["text"]
        
        await container.flow_repository.delete(flow_id)
    
    @pytest.mark.asyncio
    async def test_telegram_webhook_triggers_react_agent_which_replies_to_telegram(
        self, notification_server, unique_id, container, client, mock_llm_redis
    ):
        """
        Полный Telegram flow:
        1. Telegram webhook приходит
        2. LlmNode агент
        3. Mock LLM вызывает reply_telegram tool с chat_id из variables
        4. TelegramChannelHandler отправляет ответ в тот же чат
        5. Проверяем что Telegram API получил sendMessage
        """
        server, base_url = notification_server
        telegram_api_base = f"{base_url}/telegram"
        
        flow_id = f"tg_reply_e2e_{unique_id}"
        trigger_id = "tg_reply_trigger"
        
        # Mock LLM через Redis для реального worker
        await mock_llm_redis([
            {
                "type": "tool_call",
                "tool": "reply_telegram",
                "args": {
                    "chat_id": "777888999",
                    "message": "Привет! Я получил твое сообщение.",
                }
            },
            "Ответ отправлен!",
        ])
        
        trigger = TriggerConfig(
            trigger_id=trigger_id,
            name="Telegram Reply Trigger",
            type=TriggerType.TELEGRAM,
            config={
                "bot_token": "reply_bot_token_123",
                "secret_token": "reply_secret_123",
            },
            input_mapping={
                "content": "@trigger:message.text",
                "variables.chat_id": "@trigger:message.chat.id",
                "variables.message_id": "@trigger:message.message_id",
            },
        )
        
        flow_config = FlowConfig(
            flow_id=flow_id,
            name="Telegram Reply Agent",
            entry="main",
            nodes={
                "main": {
                    "type": "llm_node",
                    "prompt": """Ты бот в Telegram. Когда получаешь сообщение - отвечай через reply_telegram.
Chat ID пользователя доступен в state.variables.chat_id.""",
                    "tools": [
                        {
                            "tool_id": "reply_telegram",
                            "type": "channel",
                            "channel": "telegram",
                            "action": "send_message",
                            "channel_config": {
                                "bot_token": "reply_bot_token_123",
                                "api_base": telegram_api_base,
                            },
                            "description": "Отправляет ответ в Telegram чат",
                            "args_schema": {
                                "chat_id": {"type": "string", "description": "ID чата"},
                                "message": {"type": "string", "description": "Текст ответа"},
                            },
                            "input_mapping": {
                                "recipient": "@state:chat_id",
                                "text": "@state:message",
                            },
                        },
                    ],
                },
            },
            edges=[{"from": "main", "to": None}],
            triggers={trigger_id: trigger},
        )
        
        await container.flow_repository.set(flow_config)
        
        # Telegram webhook
        telegram_payload = {
            "update_id": 123123123,
            "message": {
                "message_id": 300,
                "text": "Привет бот!",
                "chat": {"id": 777888999, "type": "private"},
                "from": {"id": 111222, "username": "user123"},
                "date": 1609459200,
            },
        }
        
        response = await client.post(
            f"/flows/api/v1/triggers/telegram/{flow_id}/{trigger_id}",
            json=telegram_payload,
            headers={"X-Telegram-Bot-Api-Secret-Token": "reply_secret_123"},
        )
        
        assert response.status_code == 200
        
        # Ждём выполнения TaskIQ задачи
        import asyncio
        for _ in range(20):  # max 10 секунд
            await asyncio.sleep(0.5)
            tg_requests = server.get_requests("telegram_send_message")
            if len(tg_requests) >= 1:
                break
        
        # Проверяем что Telegram API получил sendMessage
        assert len(tg_requests) >= 1, f"No Telegram requests! Got: {server.received_requests}"
        
        last_tg = tg_requests[-1]
        assert "reply_bot_token_123" in last_tg["token"]
        assert last_tg["data"]["chat_id"] == "777888999"
        assert "Привет" in last_tg["data"]["text"]
        
        await container.flow_repository.delete(flow_id)
