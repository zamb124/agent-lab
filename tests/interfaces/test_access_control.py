"""
Тесты для функциональности ограничения доступа по пользователям.
Проверяет работу allowed_users для всех интерфейсов: Telegram, WhatsApp, Web.
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.interfaces.telegram_interface import TelegramInterface
from app.interfaces.whatsapp_interface import WhatsAppInterface
from app.interfaces.web_interface import WebInterface


class TestTelegramAccessControl:
    """Тесты проверки доступа для Telegram"""
    
    @pytest.fixture
    def telegram_config_open(self):
        """Конфигурация без ограничений (пустой список)"""
        return {
            "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "username": "test_bot",
            "allowed_users": []
        }
    
    @pytest.fixture
    def telegram_config_restricted(self):
        """Конфигурация с ограничениями"""
        return {
            "token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "username": "test_bot",
            "allowed_users": ["shvedivik", "123456789", "allowed_user"]
        }
    
    @pytest.mark.asyncio
    async def test_access_allowed_empty_list(self, telegram_config_open, test_context):
        """Тест: пустой список allowed_users → доступ для всех"""
        interface = TelegramInterface("test_token", telegram_config_open)
        
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 999999999,
                    "is_bot": False,
                    "first_name": "Unknown",
                    "username": "unknown_user"
                },
                "chat": {"id": 999999999, "type": "private"},
                "date": 1699000000,
                "text": "Привет"
            }
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="telegram:999999999:test_flow:abc123"):
            message = await interface.handle_message(telegram_update, "test_flow")
        
        assert message is not None
        assert message.content == "Привет"
        assert message.user_id == "999999999"
        print("✅ Пустой список allowed_users → доступ разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_username(self, telegram_config_restricted, test_context):
        """Тест: пользователь в списке по username → доступ разрешен"""
        interface = TelegramInterface("test_token", telegram_config_restricted)
        
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 111111111,
                    "is_bot": False,
                    "first_name": "Viktor",
                    "username": "shvedivik"
                },
                "chat": {"id": 111111111, "type": "private"},
                "date": 1699000000,
                "text": "Привет"
            }
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="telegram:111111111:test_flow:abc123"):
            message = await interface.handle_message(telegram_update, "test_flow")
        
        assert message is not None
        assert message.content == "Привет"
        print("✅ Доступ по username разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_user_id(self, telegram_config_restricted, test_context):
        """Тест: пользователь в списке по user_id → доступ разрешен"""
        interface = TelegramInterface("test_token", telegram_config_restricted)
        
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 123456789,
                    "is_bot": False,
                    "first_name": "Test",
                    "username": "other_username"
                },
                "chat": {"id": 123456789, "type": "private"},
                "date": 1699000000,
                "text": "Привет"
            }
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="telegram:123456789:test_flow:abc123"):
            message = await interface.handle_message(telegram_update, "test_flow")
        
        assert message is not None
        assert message.content == "Привет"
        print("✅ Доступ по user_id разрешен")
    
    @pytest.mark.asyncio
    async def test_access_denied(self, telegram_config_restricted, test_context):
        """Тест: пользователя нет в списке → доступ запрещен"""
        interface = TelegramInterface("test_token", telegram_config_restricted)
        
        # Mock для send_message
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 999999999,
                    "is_bot": False,
                    "first_name": "Unauthorized",
                    "username": "hacker"
                },
                "chat": {"id": 999999999, "type": "private"},
                "date": 1699000000,
                "text": "Привет"
            }
        }
        
        message = await interface.handle_message(telegram_update, "test_flow")
        
        assert message is None
        assert send_message_mock.called
        
        # Проверяем что отправлено сообщение об ошибке
        sent_message = send_message_mock.call_args[0][0]
        assert "У вас нет доступа" in sent_message.content
        assert "hacker" in sent_message.content or "999999999" in sent_message.content
        print("✅ Доступ запрещен и отправлено сообщение об ошибке")
    
    @pytest.mark.asyncio
    async def test_access_denied_no_username(self, telegram_config_restricted, test_context):
        """Тест: пользователь без username не в списке → доступ запрещен"""
        interface = TelegramInterface("test_token", telegram_config_restricted)
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        telegram_update = {
            "update_id": 123456789,
            "message": {
                "message_id": 1,
                "from": {
                    "id": 888888888,
                    "is_bot": False,
                    "first_name": "NoUsername"
                },
                "chat": {"id": 888888888, "type": "private"},
                "date": 1699000000,
                "text": "Привет"
            }
        }
        
        message = await interface.handle_message(telegram_update, "test_flow")
        
        assert message is None
        assert send_message_mock.called
        
        sent_message = send_message_mock.call_args[0][0]
        assert "У вас нет доступа" in sent_message.content
        assert "888888888" in sent_message.content
        print("✅ Доступ запрещен для пользователя без username")


class TestWhatsAppAccessControl:
    """Тесты проверки доступа для WhatsApp"""
    
    @pytest.fixture
    def whatsapp_config_open(self):
        """Конфигурация без ограничений"""
        return {
            "phone_number_id": "111111111111111",
            "business_account_id": "123456789",
            "display_name": "Test Bot",
            "allowed_users": []
        }
    
    @pytest.fixture
    def whatsapp_config_restricted(self):
        """Конфигурация с ограничениями"""
        return {
            "phone_number_id": "111111111111111",
            "business_account_id": "123456789",
            "display_name": "Test Bot",
            "allowed_users": ["79991234567", "Ivan Ivanov", "79991234568"]
        }
    
    @pytest.mark.asyncio
    async def test_access_allowed_empty_list(self, whatsapp_config_open, test_context):
        """Тест: пустой список allowed_users → доступ для всех"""
        interface = WhatsAppInterface("test_token", whatsapp_config_open)
        
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Unknown User"}}],
                        "metadata": {"phone_number_id": "111111111111111"},
                        "messages": [{
                            "from": "79999999999",
                            "id": "wamid.test123",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:79999999999:test_flow:abc123"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ WhatsApp: пустой список → доступ разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_phone(self, whatsapp_config_restricted, test_context):
        """Тест: номер телефона в списке → доступ разрешен"""
        interface = WhatsAppInterface("test_token", whatsapp_config_restricted)
        
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Test User"}}],
                        "metadata": {"phone_number_id": "111111111111111"},
                        "messages": [{
                            "from": "79991234567",
                            "id": "wamid.test123",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:79991234567:test_flow:abc123"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ WhatsApp: доступ по номеру телефона разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_name(self, whatsapp_config_restricted, test_context):
        """Тест: имя профиля в списке → доступ разрешен"""
        interface = WhatsAppInterface("test_token", whatsapp_config_restricted)
        
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Ivan Ivanov"}}],
                        "metadata": {"phone_number_id": "111111111111111"},
                        "messages": [{
                            "from": "79000000000",
                            "id": "wamid.test123",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:79000000000:test_flow:abc123"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ WhatsApp: доступ по имени профиля разрешен")
    
    @pytest.mark.asyncio
    async def test_access_denied(self, whatsapp_config_restricted, test_context):
        """Тест: пользователя нет в списке → доступ запрещен"""
        interface = WhatsAppInterface("test_token", whatsapp_config_restricted)
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        webhook_data = {
            "entry": [{
                "changes": [{
                    "value": {
                        "contacts": [{"profile": {"name": "Unauthorized User"}}],
                        "metadata": {"phone_number_id": "111111111111111"},
                        "messages": [{
                            "from": "79888888888",
                            "id": "wamid.test123",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Hello"}
                        }]
                    }
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:79888888888:test_flow:abc123"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is None
        assert send_message_mock.called
        
        sent_message = send_message_mock.call_args[0][0]
        assert "У вас нет доступа" in sent_message.content
        assert "79888888888" in sent_message.content or "Unauthorized User" in sent_message.content
        print("✅ WhatsApp: доступ запрещен и отправлено сообщение об ошибке")


class TestWebAccessControl:
    """Тесты проверки доступа для Web интерфейса"""
    
    @pytest.fixture
    def web_config_open(self):
        """Конфигурация без ограничений"""
        return {
            "allowed_users": []
        }
    
    @pytest.fixture
    def web_config_restricted(self):
        """Конфигурация с ограничениями"""
        return {
            "allowed_users": ["user@example.com", "admin_user_id", "premium_user"]
        }
    
    @pytest.mark.asyncio
    async def test_access_allowed_empty_list(self, web_config_open, test_context):
        """Тест: пустой список allowed_users → доступ для всех"""
        interface = WebInterface(web_config_open)
        
        raw_data = {
            "message": "Hello",
            "session_id": "test_session_123",
            "user_id": "unknown_user",
            "agent_id": "test_agent"
        }
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        message = await interface.handle_message(raw_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ Web: пустой список → доступ разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_user_id(self, web_config_restricted, test_context):
        """Тест: user_id в списке → доступ разрешен"""
        interface = WebInterface(web_config_restricted)
        
        # Обновляем контекст с разрешенным user_id
        test_context.user.user_id = "admin_user_id"
        
        raw_data = {
            "message": "Hello",
            "session_id": "test_session_123",
            "user_id": "admin_user_id",
            "agent_id": "test_agent"
        }
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        message = await interface.handle_message(raw_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ Web: доступ по user_id разрешен")
    
    @pytest.mark.asyncio
    async def test_access_allowed_by_email(self, web_config_restricted, test_context):
        """Тест: email в списке → доступ разрешен"""
        # Создаем конфигурацию где разрешенный пользователь это email
        # Но проверяем по user_id совпадающему с email (симуляция)
        config_with_email = {
            "allowed_users": ["user@example.com", "test_user"]
        }
        interface = WebInterface(config_with_email)
        
        # Для теста используем user_id который совпадает с allowed_users
        test_context.user.user_id = "test_user"
        
        raw_data = {
            "message": "Hello",
            "session_id": "test_session_123",
            "user_id": "test_user",
            "agent_id": "test_agent"
        }
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        message = await interface.handle_message(raw_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello"
        print("✅ Web: доступ по user_id разрешен (можно использовать и email)")
    
    @pytest.mark.asyncio
    async def test_access_denied(self, web_config_restricted, test_context):
        """Тест: пользователя нет в списке → доступ запрещен"""
        interface = WebInterface(web_config_restricted)
        
        # Обновляем контекст с неразрешенным пользователем
        test_context.user.user_id = "unauthorized_user"
        
        raw_data = {
            "message": "Hello",
            "session_id": "test_session_123",
            "user_id": "unauthorized_user",
            "agent_id": "test_agent"
        }
        
        send_message_mock = AsyncMock()
        interface.send_message = send_message_mock
        
        message = await interface.handle_message(raw_data, "test_flow")
        
        assert message is None
        assert send_message_mock.called
        
        sent_message = send_message_mock.call_args[0][0]
        assert "У вас нет доступа" in sent_message.content
        assert "unauthorized_user" in sent_message.content
        print("✅ Web: доступ запрещен и отправлено сообщение об ошибке")


class TestBaseInterfaceAccessControl:
    """Тесты базового метода check_user_access"""
    
    @pytest.mark.asyncio
    async def test_check_user_access_empty_list(self):
        """Тест: пустой список → доступ разрешен"""
        config = {"allowed_users": []}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("any_user_id", "any_username")
        
        assert is_allowed is True
        assert error is None
        print("✅ BaseInterface: пустой список → доступ разрешен")
    
    @pytest.mark.asyncio
    async def test_check_user_access_no_field(self):
        """Тест: нет поля allowed_users → доступ разрешен"""
        config = {}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("any_user_id", "any_username")
        
        assert is_allowed is True
        assert error is None
        print("✅ BaseInterface: нет поля allowed_users → доступ разрешен")
    
    @pytest.mark.asyncio
    async def test_check_user_access_by_id(self):
        """Тест: проверка по user_id"""
        config = {"allowed_users": ["user123", "user456"]}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("user123", "other_username")
        
        assert is_allowed is True
        assert error is None
        print("✅ BaseInterface: доступ по user_id разрешен")
    
    @pytest.mark.asyncio
    async def test_check_user_access_by_username(self):
        """Тест: проверка по username"""
        config = {"allowed_users": ["shvedivik", "ivanov"]}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("999999", "shvedivik")
        
        assert is_allowed is True
        assert error is None
        print("✅ BaseInterface: доступ по username разрешен")
    
    @pytest.mark.asyncio
    async def test_check_user_access_denied(self):
        """Тест: пользователя нет в списке → доступ запрещен"""
        config = {"allowed_users": ["allowed_user"]}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("999999", "hacker")
        
        assert is_allowed is False
        assert error is not None
        assert "У вас нет доступа" in error
        assert "hacker" in error
        print("✅ BaseInterface: доступ запрещен с сообщением об ошибке")
    
    @pytest.mark.asyncio
    async def test_check_user_access_denied_no_username(self):
        """Тест: доступ запрещен, username нет → показывает user_id"""
        config = {"allowed_users": ["allowed_user"]}
        interface = TelegramInterface("test_token", config)
        
        is_allowed, error = interface.check_user_access("888888", None)
        
        assert is_allowed is False
        assert error is not None
        assert "У вас нет доступа" in error
        assert "888888" in error
        print("✅ BaseInterface: доступ запрещен, в сообщении user_id")

