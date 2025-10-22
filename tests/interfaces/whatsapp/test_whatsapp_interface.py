"""
Unit тесты для WhatsAppInterface.
Полное покрытие всех методов с проверками на ошибки.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.interfaces.whatsapp_interface import WhatsAppInterface
from app.interfaces.base import Message


@pytest.fixture
def whatsapp_config():
    """Тестовая конфигурация WhatsApp"""
    return {
        "phone_number_id": "111111111111111",
        "business_account_id": "123456789",
        "verify_token": "test_verify_token_123",
        "display_name": "Test WhatsApp Bot",
        "graph_api_version": "v18.0",
        "graph_api_url": "https://graph.facebook.com"
    }


@pytest.fixture
def whatsapp_interface(whatsapp_config):
    """Экземпляр WhatsAppInterface для тестов"""
    access_token = "test_access_token_abc123"
    return WhatsAppInterface(access_token, whatsapp_config)


class TestWhatsAppInterfaceHandleMessage:
    """Тесты для метода handle_message"""
    
    @pytest.mark.asyncio
    async def test_handle_text_message(self, whatsapp_interface):
        """Тест обработки текстового сообщения"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456789",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "+1234567890",
                            "phone_number_id": "111111111111111"
                        },
                        "contacts": [{
                            "profile": {"name": "John Doe"},
                            "wa_id": "9111111111111"
                        }],
                        "messages": [{
                            "from": "9111111111111",
                            "id": "wamid.HBgNNzExMTExMTExMTExMTExMRAgAQA=",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "Hello, world!"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9111111111111:test_flow:abc123"):
            message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "Hello, world!"
        assert message.platform == "whatsapp"
        assert message.user_id == "whatsapp:9111111111111"
        assert message.metadata["phone_number"] == "9111111111111"
        assert message.metadata["profile_name"] == "John Doe"
        assert message.metadata["message_type"] == "text"
        print("✅ Текстовое сообщение обработано корректно")
    
    @pytest.mark.asyncio
    async def test_handle_empty_webhook(self, whatsapp_interface):
        """Тест обработки пустого webhook"""
        webhook_data = {}
        
        message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is None
        print("✅ Пустой webhook корректно обработан (None)")
    
    @pytest.mark.asyncio
    async def test_handle_status_update(self, whatsapp_interface):
        """Тест обработки статуса доставки (не создает Message)"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "123456789",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "+1234567890",
                            "phone_number_id": "111111111111111"
                        },
                        "statuses": [{
                            "id": "wamid.xxx",
                            "status": "delivered",
                            "timestamp": "1699000001",
                            "recipient_id": "9111111111111"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is None
        print("✅ Статус доставки обработан (не создает Message)")
    
    @pytest.mark.asyncio
    async def test_handle_image_message(self, whatsapp_interface):
        """Тест обработки изображения"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "111111111111111"
                        },
                        "contacts": [{
                            "profile": {"name": "Jane Doe"},
                            "wa_id": "9222222222222"
                        }],
                        "messages": [{
                            "from": "9222222222222",
                            "id": "wamid.IMAGE123",
                            "timestamp": "1699000002",
                            "type": "image",
                            "image": {
                                "id": "media_123",
                                "mime_type": "image/jpeg",
                                "caption": "Check this photo"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9222222222222:test_flow:xyz"):
            with patch.object(whatsapp_interface, 'process_files', return_value=["📷 Image processed"]):
                message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "Check this photo" in message.content
        assert message.metadata["message_type"] == "image"
        print("✅ Изображение обработано корректно")
    
    @pytest.mark.asyncio
    async def test_handle_audio_message(self, whatsapp_interface):
        """Тест обработки аудио сообщения"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "phone_number_id": "111111111111111"
                        },
                        "contacts": [{
                            "profile": {"name": "Audio User"},
                            "wa_id": "9333333333333"
                        }],
                        "messages": [{
                            "from": "9333333333333",
                            "id": "wamid.AUDIO456",
                            "timestamp": "1699000003",
                            "type": "audio",
                            "audio": {
                                "id": "media_audio_789",
                                "mime_type": "audio/ogg; codecs=opus"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9333333333333:test_flow:audio"):
            with patch.object(whatsapp_interface, 'process_audio_files', return_value=["🎤 Audio recognized: Hello"]):
                message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "🎤 Audio recognized" in message.content or message.files
        print("✅ Аудио сообщение обработано корректно")
    
    @pytest.mark.asyncio
    async def test_handle_command_message(self, whatsapp_interface):
        """Тест обработки команды (/start, /help, /clear)"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9444444444444"}],
                        "messages": [{
                            "from": "9444444444444",
                            "id": "wamid.CMD",
                            "timestamp": "1699000004",
                            "type": "text",
                            "text": {"body": "/help"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9444444444444:test_flow:cmd"):
            with patch.object(whatsapp_interface, 'send_message') as mock_send:
                message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        # Команда обрабатывается и не создает Message (возвращает None)
        assert message is None
        # Но отправляет ответ на команду
        assert mock_send.called
        print("✅ Команда обработана корректно")
    
    @pytest.mark.asyncio
    async def test_handle_location_message(self, whatsapp_interface):
        """Тест обработки геолокации"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9555555555555"}],
                        "messages": [{
                            "from": "9555555555555",
                            "id": "wamid.LOC",
                            "timestamp": "1699000005",
                            "type": "location",
                            "location": {
                                "latitude": 55.7558,
                                "longitude": 37.6173,
                                "name": "Red Square",
                                "address": "Moscow, Russia"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9555555555555:test_flow:loc"):
            message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "📍 Локация" in message.content
        assert "Red Square" in message.content
        assert "Moscow, Russia" in message.content
        assert "55.7558" in message.content
        assert "37.6173" in message.content
        print("✅ Локация обработана корректно")
    
    @pytest.mark.asyncio
    async def test_handle_button_reply(self, whatsapp_interface):
        """Тест обработки ответа на кнопку"""
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9666666666666"}],
                        "messages": [{
                            "from": "9666666666666",
                            "id": "wamid.BTN",
                            "timestamp": "1699000006",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {
                                    "id": "btn_weather",
                                    "title": "Узнать погоду"
                                }
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(whatsapp_interface, 'get_or_create_session', return_value="whatsapp:9666666666666:test_flow:btn"):
            message = await whatsapp_interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "Узнать погоду"
        print("✅ Button reply обработан корректно")


class TestWhatsAppInterfaceSendMessage:
    """Тесты для метода send_message"""
    
    @pytest.mark.asyncio
    async def test_send_text_message(self, whatsapp_interface):
        """Тест отправки текстового сообщения"""
        message = Message(
            user_id="whatsapp:9111111111111",
            session_id="whatsapp:9111111111111:test_flow:abc",
            content="Hello from bot!",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={"phone_number": "9111111111111"}
        )
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"messages": [{"id": "wamid.sent123"}]})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            await whatsapp_interface.send_message(message)
        
        print("✅ Текстовое сообщение отправлено")
    
    @pytest.mark.asyncio
    async def test_send_message_without_phone_number(self, whatsapp_interface):
        """Тест отправки без phone_number должен бросить исключение"""
        message = Message(
            user_id="whatsapp:unknown",
            session_id="test_session",
            content="Test",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={}  # Нет phone_number!
        )
        
        with pytest.raises(ValueError, match="phone_number обязателен"):
            await whatsapp_interface.send_message(message)
        
        print("✅ Исключение при отсутствии phone_number")
    
    @pytest.mark.asyncio
    async def test_send_message_with_buttons(self, whatsapp_interface):
        """Тест отправки интерактивного сообщения с кнопками"""
        message = Message(
            user_id="whatsapp:9111111111111",
            session_id="whatsapp:9111111111111:test_flow:btn",
            content="Choose action:",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={
                "phone_number": "9111111111111",
                "buttons": [
                    {"id": "btn_1", "text": "Option 1"},
                    {"id": "btn_2", "text": "Option 2"}
                ]
            }
        )
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"messages": [{"id": "wamid.interactive123"}]})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            await whatsapp_interface.send_message(message)
        
        print("✅ Интерактивное сообщение с кнопками отправлено")
    
    @pytest.mark.asyncio
    async def test_send_message_with_many_buttons_list(self, whatsapp_interface):
        """Тест отправки списка (более 3 кнопок)"""
        buttons = [
            {"id": f"btn_{i}", "text": f"Option {i}"} 
            for i in range(1, 6)  # 5 кнопок
        ]
        
        message = Message(
            user_id="whatsapp:9111111111111",
            session_id="test_session",
            content="Choose from list:",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={
                "phone_number": "9111111111111",
                "buttons": buttons
            }
        )
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"messages": [{"id": "wamid.list123"}]})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            await whatsapp_interface.send_message(message)
        
        print("✅ List message (5 кнопок) отправлен")
    
    @pytest.mark.asyncio
    async def test_send_message_with_markdown_formatting(self, whatsapp_interface):
        """Тест конвертации Markdown в WhatsApp форматирование"""
        message = Message(
            user_id="whatsapp:9111111111111",
            session_id="test_session",
            content="**Bold text** and _italic text_",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={"phone_number": "9111111111111"}
        )
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"messages": [{"id": "wamid.fmt123"}]})
        
        sent_payload = None
        
        async def capture_post(url, json=None, **kwargs):
            nonlocal sent_payload
            sent_payload = json
            return mock_response
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = capture_post
            
            await whatsapp_interface.send_message(message)
        
        # Проверяем что Markdown конвертирован
        assert sent_payload is not None
        text_sent = sent_payload["text"]["body"]
        assert "*Bold text*" in text_sent  # **bold** -> *bold*
        assert "_italic text_" in text_sent
        print("✅ Markdown корректно конвертирован в WhatsApp формат")


class TestWhatsAppInterfaceMediaProcessing:
    """Тесты обработки медиа"""
    
    @pytest.mark.asyncio
    async def test_get_media_url_success(self, whatsapp_interface):
        """Тест успешного получения URL медиа"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={
            "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/media_123",
            "mime_type": "image/jpeg",
            "file_size": 12345
        })
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            url = await whatsapp_interface._get_media_url("media_123")
        
        assert url == "https://lookaside.fbsbx.com/whatsapp_business/attachments/media_123"
        print("✅ Media URL получен успешно")
    
    @pytest.mark.asyncio
    async def test_get_media_url_api_error(self, whatsapp_interface):
        """Тест ошибки API при получении URL медиа"""
        mock_response = AsyncMock()
        mock_response.status_code = 404
        mock_response.text = "Media not found"
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            with pytest.raises(Exception):
                await whatsapp_interface._get_media_url("invalid_media_id")
        
        print("✅ Исключение при ошибке API получения медиа")
    
    @pytest.mark.asyncio
    async def test_get_media_url_no_url_in_response(self, whatsapp_interface):
        """Тест когда API не вернул URL"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={})  # Нет URL!
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            with pytest.raises(ValueError, match="не вернул URL"):
                await whatsapp_interface._get_media_url("media_no_url")
        
        print("✅ Исключение когда API не вернул URL")
    
    @pytest.mark.asyncio
    async def test_upload_media_success(self, whatsapp_interface):
        """Тест успешной загрузки медиа в WhatsApp"""
        media_data = b"fake audio data"
        mime_type = "audio/ogg; codecs=opus"
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"id": "uploaded_media_999"})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            media_id = await whatsapp_interface._upload_media(media_data, mime_type)
        
        assert media_id == "uploaded_media_999"
        print("✅ Медиа успешно загружено в WhatsApp")
    
    @pytest.mark.asyncio
    async def test_upload_media_api_error(self, whatsapp_interface):
        """Тест ошибки при загрузке медиа"""
        media_data = b"fake data"
        mime_type = "audio/ogg"
        
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = "Invalid media format"
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            with pytest.raises(Exception):
                await whatsapp_interface._upload_media(media_data, mime_type)
        
        print("✅ Исключение при ошибке загрузки медиа")
    
    @pytest.mark.asyncio
    async def test_upload_media_no_id_in_response(self, whatsapp_interface):
        """Тест когда API не вернул media_id"""
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={})  # Нет id!
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            with pytest.raises(ValueError, match="не вернул media_id"):
                await whatsapp_interface._upload_media(b"data", "audio/ogg")
        
        print("✅ Исключение когда API не вернул media_id")


class TestWhatsAppInterfaceTypingNotification:
    """Тесты для typing notification"""
    
    @pytest.mark.asyncio
    async def test_typing_notification(self, whatsapp_interface):
        """Тест отправки typing индикатора"""
        session_id = "whatsapp:9111111111111:test_flow:typing"
        
        # В WhatsApp это просто логируется (нет API для typing)
        await whatsapp_interface.send_typing_notification(session_id, True)
        await whatsapp_interface.send_typing_notification(session_id, False)
        
        print("✅ Typing notification обработан")
    
    @pytest.mark.asyncio
    async def test_typing_notification_invalid_session(self, whatsapp_interface):
        """Тест typing с неверным форматом session_id"""
        invalid_session_id = "telegram:123:flow:abc"  # Не whatsapp!
        
        # Должен логировать warning и не падать
        await whatsapp_interface.send_typing_notification(invalid_session_id, True)
        
        print("✅ Некорректный session_id обработан без падения")


class TestWhatsAppInterfaceFormatting:
    """Тесты форматирования"""
    
    def test_convert_markdown_to_whatsapp(self, whatsapp_interface):
        """Тест конвертации Markdown"""
        # **bold** -> *bold*
        result = whatsapp_interface._convert_markdown_to_whatsapp("**Bold text**")
        assert result == "*Bold text*"
        
        # __italic__ -> _italic_
        result = whatsapp_interface._convert_markdown_to_whatsapp("__Italic text__")
        assert result == "_Italic text_"
        
        # Комбинация
        result = whatsapp_interface._convert_markdown_to_whatsapp("**Bold** and __italic__")
        assert result == "*Bold* and _italic_"
        
        print("✅ Markdown корректно конвертируется")


class TestWhatsAppInterfaceCredentials:
    """Тесты работы с credentials"""
    
    @pytest.mark.asyncio
    async def test_get_access_token_with_variable(self):
        """Тест резолва access_token через переменную"""
        platform_config = {
            "access_token": "@var:whatsapp_token"
        }
        
        with patch('app.interfaces.whatsapp_interface.get_container') as mock_container:
            mock_vars = AsyncMock()
            mock_vars.resolve = AsyncMock(return_value="resolved_token_123")
            mock_container.return_value.variables_service = mock_vars
            
            token = await WhatsAppInterface.get_access_token_for_flow("test_flow", platform_config)
        
        assert token == "resolved_token_123"
        print("✅ Access token резолвнут через переменную")
    
    @pytest.mark.asyncio
    async def test_get_access_token_hardcoded(self):
        """Тест получения хардкоженного токена"""
        platform_config = {
            "access_token": "hardcoded_token_xyz"
        }
        
        with patch('app.interfaces.whatsapp_interface.get_container') as mock_container:
            mock_vars = AsyncMock()
            mock_vars.resolve = AsyncMock(return_value="hardcoded_token_xyz")
            mock_container.return_value.variables_service = mock_vars
            
            token = await WhatsAppInterface.get_access_token_for_flow("test_flow", platform_config)
        
        assert token == "hardcoded_token_xyz"
        print("✅ Хардкоженный токен получен")
    
    @pytest.mark.asyncio
    async def test_get_access_token_missing(self):
        """Тест отсутствия токена должен бросить исключение"""
        platform_config = {}  # Нет access_token!
        
        with pytest.raises(ValueError, match="No access_token"):
            await WhatsAppInterface.get_access_token_for_flow("test_flow", platform_config)
        
        print("✅ Исключение при отсутствии access_token")
    
    @pytest.mark.asyncio
    async def test_verify_webhook_token(self):
        """Тест верификации webhook token"""
        result = await WhatsAppInterface.verify_webhook_token("test123", "test123")
        assert result is True
        
        result = await WhatsAppInterface.verify_webhook_token("test123", "wrong")
        assert result is False
        
        print("✅ Verify token проверяется корректно")
    
    @pytest.mark.asyncio
    async def test_verify_webhook_signature(self):
        """Тест верификации webhook подписи"""
        payload = b'{"test": "data"}'
        app_secret = "my_app_secret"
        
        import hmac
        import hashlib
        
        # Создаем валидную подпись
        signature = hmac.new(app_secret.encode(), payload, hashlib.sha256).hexdigest()
        
        result = await WhatsAppInterface.verify_webhook_signature(payload, signature, app_secret)
        assert result is True
        
        # Неверная подпись
        result = await WhatsAppInterface.verify_webhook_signature(payload, "wrong_signature", app_secret)
        assert result is False
        
        # С префиксом sha256=
        signature_with_prefix = f"sha256={signature}"
        result = await WhatsAppInterface.verify_webhook_signature(payload, signature_with_prefix, app_secret)
        assert result is True
        
        print("✅ Webhook signature верифицируется корректно")


class TestWhatsAppInterfaceRegistration:
    """Тесты регистрации WhatsApp"""
    
    @pytest.mark.asyncio
    async def test_register_flow_success(self):
        """Тест успешной регистрации flow"""
        flow_id = "test_flow"
        username = "Test Bot"
        platform_config = {
            "phone_number_id": "111111111111111",
            "access_token": "test_token",
            "graph_api_url": "https://graph.facebook.com",
            "graph_api_version": "v18.0"
        }
        
        mock_phone_response = AsyncMock()
        mock_phone_response.status_code = 200
        mock_phone_response.json = MagicMock(return_value={
            "id": "111111111111111",
            "display_phone_number": "+1234567890",
            "verified_name": "Test Company"
        })
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_phone_response)
            
            with patch('app.db.repositories.Storage.list_by_prefix') as mock_list:
                mock_list.return_value = ["company:test:flow:test_flow"]
                
                result = await WhatsAppInterface.register(flow_id, username, platform_config)
        
        assert result["success"] is True
        assert result["platform"] == "whatsapp"
        assert "phone_number" in result
        print("✅ Регистрация flow успешна")
    
    @pytest.mark.asyncio
    async def test_register_flow_invalid_credentials(self):
        """Тест регистрации с невалидными credentials"""
        flow_id = "test_flow"
        platform_config = {
            "phone_number_id": "invalid_id",
            "access_token": "invalid_token"
        }
        
        mock_response = AsyncMock()
        mock_response.status_code = 401
        mock_response.text = "Invalid OAuth access token"
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            with pytest.raises(Exception):
                await WhatsAppInterface.register(flow_id, "Bot", platform_config)
        
        print("✅ Исключение при невалидных credentials")
    
    @pytest.mark.asyncio
    async def test_register_missing_phone_number_id(self):
        """Тест регистрации без phone_number_id"""
        platform_config = {
            "access_token": "test_token"
            # Нет phone_number_id!
        }
        
        with patch('app.services.variables_service.get_variables_service') as mock_service:
            mock_vars = AsyncMock()
            mock_vars.resolve.return_value = "test_token"
            mock_service.return_value = mock_vars
            
            with pytest.raises(ValueError, match="phone_number_id not found"):
                await WhatsAppInterface.register("test_flow", "Bot", platform_config)
        
        print("✅ Исключение при отсутствии phone_number_id")


class TestWhatsAppInterfaceExtractMessageContent:
    """Тесты извлечения контента из разных типов сообщений"""
    
    @pytest.mark.asyncio
    async def test_extract_text_message(self, whatsapp_interface):
        """Тест извлечения текста"""
        wa_message = {
            "type": "text",
            "text": {"body": "Hello WhatsApp!"}
        }
        
        content, files = await whatsapp_interface._extract_message_content(wa_message, "text", "user123")
        
        assert content == "Hello WhatsApp!"
        assert files == []
        print("✅ Текст извлечен корректно")
    
    @pytest.mark.asyncio
    async def test_extract_video_message(self, whatsapp_interface):
        """Тест извлечения видео с caption"""
        wa_message = {
            "type": "video",
            "video": {
                "id": "video_123",
                "mime_type": "video/mp4",
                "caption": "Watch this video"
            }
        }
        
        content, files = await whatsapp_interface._extract_message_content(wa_message, "video", "user123")
        
        assert content == "Watch this video"
        assert len(files) == 1
        assert files[0]["type"] == "video"
        assert files[0]["media_id"] == "video_123"
        print("✅ Видео с caption извлечено корректно")
    
    @pytest.mark.asyncio
    async def test_extract_document_message(self, whatsapp_interface):
        """Тест извлечения документа"""
        wa_message = {
            "type": "document",
            "document": {
                "id": "doc_456",
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "caption": "Important report"
            }
        }
        
        content, files = await whatsapp_interface._extract_message_content(wa_message, "document", "user123")
        
        assert content == "Important report"
        assert len(files) == 1
        assert files[0]["type"] == "document"
        assert files[0]["filename"] == "report.pdf"
        print("✅ Документ извлечен корректно")
    
    @pytest.mark.asyncio
    async def test_extract_contacts_message(self, whatsapp_interface):
        """Тест извлечения контактов"""
        wa_message = {
            "type": "contacts",
            "contacts": [{
                "name": {"formatted_name": "John Smith"},
                "phones": [{"phone": "+1234567890"}]
            }]
        }
        
        content, files = await whatsapp_interface._extract_message_content(wa_message, "contacts", "user123")
        
        assert "👤 Контакты" in content
        assert "John Smith" in content
        assert "+1234567890" in content
        print("✅ Контакты извлечены корректно")


class TestWhatsAppInterfaceProcessFiles:
    """Тесты обработки файлов"""
    
    @pytest.mark.asyncio
    async def test_process_single_file(self, whatsapp_interface):
        """Тест обработки одного файла"""
        file_data = {
            "type": "image",
            "media_id": "media_img_123",
            "mime_type": "image/jpeg",
            "filename": "photo.jpg"
        }
        
        mock_file_processor = AsyncMock()
        mock_file_record = MagicMock()
        mock_file_record.file_id = "processed_file_123"
        mock_file_processor.process_file_from_url.return_value = mock_file_record
        
        with patch.object(whatsapp_interface, '_get_media_url', return_value="https://example.com/media_img_123"):
            result = await whatsapp_interface._process_single_file(file_data, "user123", mock_file_processor)
        
        assert result == mock_file_record
        mock_file_processor.process_file_from_url.assert_called_once()
        print("✅ Файл обработан через FileProcessor")
    
    @pytest.mark.asyncio
    async def test_process_single_file_no_media_id(self, whatsapp_interface):
        """Тест обработки файла без media_id должен бросить исключение"""
        file_data = {
            "type": "image"
            # Нет media_id!
        }
        
        with pytest.raises(ValueError, match="media_id обязателен"):
            await whatsapp_interface._process_single_file(file_data, "user123", AsyncMock())
        
        print("✅ Исключение при отсутствии media_id")
    
    @pytest.mark.asyncio
    async def test_process_single_audio_file(self, whatsapp_interface):
        """Тест обработки аудиофайла"""
        audio_data = {
            "type": "voice",
            "media_id": "media_voice_789",
            "mime_type": "audio/ogg; codecs=opus"
        }
        
        mock_audio_processor = AsyncMock()
        mock_audio_record = MagicMock()
        mock_audio_record.audio_id = "processed_audio_789"
        mock_audio_processor.process_audio_from_url.return_value = mock_audio_record
        
        with patch.object(whatsapp_interface, '_get_media_url', return_value="https://example.com/media_voice_789"):
            result = await whatsapp_interface._process_single_audio_file(audio_data, "user123", mock_audio_processor)
        
        assert result == mock_audio_record
        mock_audio_processor.process_audio_from_url.assert_called_once()
        
        # Проверяем что auto_recognize=True
        call_kwargs = mock_audio_processor.process_audio_from_url.call_args.kwargs
        assert call_kwargs["auto_recognize"] is True
        print("✅ Аудио обработано через AudioProcessor с распознаванием")
    
    @pytest.mark.asyncio
    async def test_process_audio_file_no_media_id(self, whatsapp_interface):
        """Тест обработки аудио без media_id должен бросить исключение"""
        audio_data = {
            "type": "audio"
            # Нет media_id!
        }
        
        with pytest.raises(ValueError, match="media_id обязателен"):
            await whatsapp_interface._process_single_audio_file(audio_data, "user123", AsyncMock())
        
        print("✅ Исключение при отсутствии media_id в аудио")


class TestWhatsAppInterfaceSendAudio:
    """Тесты отправки аудиофайлов"""
    
    @pytest.mark.asyncio
    async def test_send_audio_message_success(self, whatsapp_interface):
        """Тест успешной отправки аудио"""
        phone_number = "9111111111111"
        audio_info = {"audio_id": "audio_123"}
        metadata = {}
        
        mock_audio_record = MagicMock()
        mock_audio_record.audio_id = "audio_123"
        mock_audio_record.s3_key = "audio/audio_123.ogg"
        mock_audio_record.content_type = "audio/ogg; codecs=opus"
        
        mock_audio_processor = AsyncMock()
        mock_audio_processor.get_audio_record = AsyncMock(return_value=mock_audio_record)
        
        mock_s3_client = AsyncMock()
        mock_s3_client.download_bytes = AsyncMock(return_value=b"fake audio bytes")
        mock_audio_processor._get_s3_client = AsyncMock(return_value=mock_s3_client)
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 200
        mock_api_response.json = MagicMock(return_value={"messages": [{"id": "wamid.audio"}]})
        
        with patch('app.interfaces.whatsapp_interface.get_default_audio_processor', return_value=mock_audio_processor):
            with patch.object(whatsapp_interface, '_upload_media', return_value="uploaded_media_456"):
                with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_api_response)
                    
                    await whatsapp_interface._send_audio_message(phone_number, audio_info, metadata)
        
        print("✅ Аудио сообщение отправлено успешно")
    
    @pytest.mark.asyncio
    async def test_send_audio_message_not_found(self, whatsapp_interface):
        """Тест отправки несуществующего аудио должен бросить исключение"""
        audio_info = {"audio_id": "nonexistent_audio"}
        
        mock_audio_processor = AsyncMock()
        mock_audio_processor.get_audio_record = AsyncMock(return_value=None)  # Аудио не найдено!
        
        with patch('app.interfaces.whatsapp_interface.get_default_audio_processor', return_value=mock_audio_processor):
            with pytest.raises(ValueError, match="не найден в системе"):
                await whatsapp_interface._send_audio_message("9111111111111", audio_info, {})
        
        print("✅ Исключение при отсутствии аудио в системе")
    
    @pytest.mark.asyncio
    async def test_send_audio_s3_download_failed(self, whatsapp_interface):
        """Тест когда не удается скачать аудио из S3"""
        audio_info = {"audio_id": "audio_s3_fail"}
        
        mock_audio_record = MagicMock()
        mock_audio_record.audio_id = "audio_s3_fail"
        mock_audio_record.s3_key = "audio/fail.ogg"
        
        mock_audio_processor = AsyncMock()
        mock_audio_processor.get_audio_record = AsyncMock(return_value=mock_audio_record)
        
        mock_s3_client = AsyncMock()
        mock_s3_client.download_bytes = AsyncMock(return_value=None)  # Не удалось скачать!
        mock_audio_processor._get_s3_client = AsyncMock(return_value=mock_s3_client)
        
        with patch('app.interfaces.whatsapp_interface.get_default_audio_processor', return_value=mock_audio_processor):
            with pytest.raises(ValueError, match="Не удалось скачать аудиофайл.*из S3"):
                await whatsapp_interface._send_audio_message("9111111111111", audio_info, {})
        
        print("✅ Исключение при ошибке скачивания из S3")
    
    @pytest.mark.asyncio
    async def test_send_audio_upload_failed(self, whatsapp_interface):
        """Тест когда не удается загрузить аудио в WhatsApp"""
        audio_info = {"audio_id": "audio_upload_fail"}
        
        mock_audio_record = MagicMock()
        mock_audio_record.audio_id = "audio_upload_fail"
        mock_audio_record.s3_key = "audio/fail.ogg"
        mock_audio_record.content_type = "audio/ogg"
        
        mock_audio_processor = AsyncMock()
        mock_audio_processor.get_audio_record = AsyncMock(return_value=mock_audio_record)
        
        mock_s3_client = AsyncMock()
        mock_s3_client.download_bytes = AsyncMock(return_value=b"audio bytes")
        mock_audio_processor._get_s3_client = AsyncMock(return_value=mock_s3_client)
        
        with patch('app.interfaces.whatsapp_interface.get_default_audio_processor', return_value=mock_audio_processor):
            with patch.object(whatsapp_interface, '_upload_media', return_value=None):  # Загрузка не удалась!
                with pytest.raises(ValueError, match="Не удалось загрузить аудио в WhatsApp API"):
                    await whatsapp_interface._send_audio_message("9111111111111", audio_info, {})
        
        print("✅ Исключение при ошибке загрузки в WhatsApp API")


class TestWhatsAppInterfaceStatusUpdates:
    """Тесты обработки статусов"""
    
    @pytest.mark.asyncio
    async def test_handle_delivered_status(self, whatsapp_interface):
        """Тест обработки статуса delivered"""
        statuses = [{
            "id": "wamid.msg123",
            "status": "delivered",
            "timestamp": "1699000010",
            "recipient_id": "9111111111111"
        }]
        
        # Не должно бросать исключений
        await whatsapp_interface._handle_status_update(statuses)
        print("✅ Статус delivered обработан")
    
    @pytest.mark.asyncio
    async def test_handle_failed_status(self, whatsapp_interface):
        """Тест обработки статуса failed с ошибками"""
        statuses = [{
            "id": "wamid.msg456",
            "status": "failed",
            "timestamp": "1699000011",
            "recipient_id": "9222222222222",
            "errors": [{
                "code": 131049,
                "title": "Message not delivered",
                "message": "Failed to deliver"
            }]
        }]
        
        # Не должно бросать исключений, только логирование
        await whatsapp_interface._handle_status_update(statuses)
        print("✅ Статус failed с ошибками обработан")


class TestWhatsAppInterfaceCommands:
    """Тесты команд (наследуются от BaseInterface)"""
    
    @pytest.mark.asyncio
    async def test_setup_commands(self, whatsapp_interface):
        """Тест setup_commands (WhatsApp не поддерживает установку команд через API)"""
        result = await whatsapp_interface.setup_commands()
        
        assert result is True
        print("✅ setup_commands возвращает True (команды обрабатываются автоматически)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

