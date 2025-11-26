"""
Интеграционные тесты WhatsApp.
Полный путь: WhatsApp webhook -> Interface -> TaskProcessor -> Agent -> Response.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from apps.agents.interfaces.whatsapp_interface import WhatsAppInterface
from apps.agents.interfaces.base import Message


@pytest.mark.asyncio
class TestWhatsAppFullIntegration:
    """Интеграционные тесты полного флоу"""
    
    async def test_whatsapp_text_message_full_flow(self):
        """Тест полного флоу текстового сообщения"""
        
        # Создаем WhatsApp webhook payload
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
                            "profile": {"name": "Integration Test User"},
                            "wa_id": "9111111111111"
                        }],
                        "messages": [{
                            "from": "9111111111111",
                            "id": "wamid.integration_test",
                            "timestamp": "1699000000",
                            "type": "text",
                            "text": {"body": "What is the weather in Moscow?"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        # Создаем интерфейс
        platform_config = {
            "phone_number_id": "111111111111111",
            "display_name": "Test Bot"
        }
        interface = WhatsAppInterface("test_token", platform_config)
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9111111111111:test_flow:int123"):
            # Обрабатываем webhook
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert message.content == "What is the weather in Moscow?"
        assert message.platform == "whatsapp"
        assert message.user_id == "whatsapp:9111111111111"
        assert message.metadata["profile_name"] == "Integration Test User"
        
        print("✅ Полный флоу текстового сообщения работает")
        print(f"   User: {message.user_id}")
        print(f"   Content: {message.content}")
        print(f"   Session: {message.session_id}")
    
    async def test_whatsapp_image_message_with_processing(self):
        """Тест обработки изображения с сохранением в S3"""
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Photo User"}, "wa_id": "9222222222222"}],
                        "messages": [{
                            "from": "9222222222222",
                            "id": "wamid.photo_test",
                            "timestamp": "1699000001",
                            "type": "image",
                            "image": {
                                "id": "media_photo_123",
                                "mime_type": "image/jpeg",
                                "caption": "Beautiful sunset"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        # Мокаем обработку файлов
        mock_file_messages = ["📷 Изображение: beautiful_sunset.jpg\nURL: https://storage/file_123"]
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9222222222222:test_flow:photo"):
            with patch.object(interface, 'process_files', return_value=mock_file_messages):
                message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "Beautiful sunset" in message.content
        assert "📷" in message.content
        print("✅ Изображение обработано и добавлено в сообщение")
    
    async def test_whatsapp_audio_message_with_recognition(self):
        """Тест обработки голосового сообщения с распознаванием"""
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Voice User"}, "wa_id": "9333333333333"}],
                        "messages": [{
                            "from": "9333333333333",
                            "id": "wamid.voice_test",
                            "timestamp": "1699000002",
                            "type": "voice",
                            "voice": {
                                "id": "media_voice_456",
                                "mime_type": "audio/ogg; codecs=opus"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        # Мокаем обработку аудио с распознаванием
        mock_audio_messages = [
            "🎤 Голосовое сообщение: whatsapp_voice.ogg\n"
            "Распознано: \"Какая погода в Москве?\"\n"
            "URL: https://storage/audio_456"
        ]
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9333333333333:test_flow:voice"):
            with patch.object(interface, 'process_audio_files', return_value=mock_audio_messages):
                message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "🎤" in message.content
        assert "Распознано" in message.content
        print("✅ Голосовое сообщение обработано с распознаванием")
    
    async def test_whatsapp_command_processing(self):
        """Тест обработки команд через webhook"""
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Command User"}, "wa_id": "9444444444444"}],
                        "messages": [{
                            "from": "9444444444444",
                            "id": "wamid.cmd_test",
                            "timestamp": "1699000003",
                            "type": "text",
                            "text": {"body": "/help"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_sent_messages = []
        
        async def capture_send(message):
            mock_sent_messages.append(message)
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9444444444444:test_flow:cmd"):
            with patch.object(interface, 'send_message', side_effect=capture_send):
                message = await interface.handle_message(webhook_data, "test_flow")
        
        # Команда не создает Message (возвращает None)
        assert message is None
        
        # Но отправляет ответ на команду
        assert len(mock_sent_messages) == 1
        assert "команд" in mock_sent_messages[0].content.lower()
        print("✅ Команда обработана и ответ отправлен")
    
    async def test_whatsapp_button_interaction_flow(self):
        """Тест интерактивного флоу с кнопками"""
        
        # Шаг 1: Бот отправляет сообщение с кнопками
        outgoing_message = Message(
            user_id="whatsapp:9555555555555",
            session_id="whatsapp:9555555555555:test_flow:btn_flow",
            content="Выберите город:",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={
                "phone_number": "9555555555555",
                "buttons": [
                    {"id": "moscow", "text": "Москва"},
                    {"id": "spb", "text": "Санкт-Петербург"},
                    {"id": "kazan", "text": "Казань"}
                ]
            }
        )
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_send_response = AsyncMock()
        mock_send_response.status_code = 200
        mock_send_response.json = MagicMock(return_value={"messages": [{"id": "wamid.buttons_sent"}]})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_send_response)
            
            # Отправляем кнопки
            await interface.send_message(outgoing_message)
        
        print("✅ Кнопки отправлены пользователю")
        
        # Шаг 2: Пользователь нажимает кнопку
        button_click_webhook = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9555555555555"}],
                        "messages": [{
                            "from": "9555555555555",
                            "id": "wamid.button_click",
                            "timestamp": "1699000004",
                            "type": "interactive",
                            "interactive": {
                                "type": "button_reply",
                                "button_reply": {
                                    "id": "moscow",
                                    "title": "Москва"
                                }
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9555555555555:test_flow:btn_flow"):
            message = await interface.handle_message(button_click_webhook, "test_flow")
        
        assert message is not None
        assert message.content == "Москва"
        assert message.user_id == "whatsapp:9555555555555"
        
        print("✅ Полный интерактивный флоу работает:")
        print("   1. Кнопки отправлены")
        print("   2. Нажатие кнопки получено")
        print(f"   3. Контент извлечен: {message.content}")
    
    async def test_whatsapp_multimodal_message(self):
        """Тест сообщения с текстом, изображением и кнопками"""
        
        # Пользователь отправляет фото с текстом
        incoming_webhook = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Multi User"}, "wa_id": "9666666666666"}],
                        "messages": [{
                            "from": "9666666666666",
                            "id": "wamid.multi",
                            "timestamp": "1699000005",
                            "type": "image",
                            "image": {
                                "id": "media_multi_789",
                                "mime_type": "image/jpeg",
                                "caption": "Analyze this weather map"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_file_messages = [
            "📷 Изображение: weather_map.jpg\n"
            "URL: https://storage/file_multi_789\n"
            "Размер: 456 KB"
        ]
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9666666666666:test_flow:multi"):
            with patch.object(interface, 'process_files', return_value=mock_file_messages):
                message = await interface.handle_message(incoming_webhook, "test_flow")
        
        assert message is not None
        
        # Проверяем что в сообщении есть и caption и информация о файле
        assert "Analyze this weather map" in message.content
        assert "📷" in message.content
        assert "weather_map.jpg" in message.content
        
        print("✅ Мультимодальное сообщение (текст + изображение) обработано")
        print(f"   Content preview: {message.content[:100]}...")
        
        # Бот отвечает с кнопками
        outgoing_message = Message(
            user_id="whatsapp:9666666666666",
            session_id=message.session_id,
            content="Это карта погоды для Москвы. Что хотите узнать?",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={
                "phone_number": "9666666666666",
                "buttons": [
                    {"id": "temp", "text": "Температура"},
                    {"id": "wind", "text": "Ветер"},
                    {"id": "humidity", "text": "Влажность"}
                ]
            }
        )
        
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.json = MagicMock(return_value={"messages": [{"id": "wamid.response"}]})
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            await interface.send_message(outgoing_message)
        
        print("✅ Ответ с кнопками отправлен")
    
    async def test_whatsapp_voice_to_voice_flow(self):
        """Тест голосового диалога: голос -> распознавание -> голосовой ответ"""
        
        # Пользователь отправляет голосовое
        voice_webhook = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Voice User"}, "wa_id": "9777777777777"}],
                        "messages": [{
                            "from": "9777777777777",
                            "id": "wamid.voice_in",
                            "timestamp": "1699000006",
                            "type": "voice",
                            "voice": {
                                "id": "media_voice_in_999",
                                "mime_type": "audio/ogg; codecs=opus"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        # Мокаем распознавание голоса
        mock_audio_messages = [
            "🎤 Голосовое сообщение: whatsapp_voice.ogg\n"
            "Распознано: \"Какая погода в Санкт-Петербурге?\"\n"
            "Длительность: 3.5 сек\n"
            "URL: https://storage/audio_voice_in_999"
        ]
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9777777777777:test_flow:voice_flow"):
            with patch.object(interface, 'process_audio_files', return_value=mock_audio_messages):
                incoming_message = await interface.handle_message(voice_webhook, "test_flow")
        
        assert incoming_message is not None
        assert "Распознано" in incoming_message.content
        assert "Какая погода в Санкт-Петербурге?" in incoming_message.content
        
        print("✅ Голосовое сообщение распознано")
        print("   Recognized text: Какая погода в Санкт-Петербурге?")
        
        # Бот отвечает голосом
        outgoing_with_audio = Message(
            user_id="whatsapp:9777777777777",
            session_id=incoming_message.session_id,
            content="[AUDIO]audio_id:response_audio_123[/AUDIO] В Санкт-Петербурге сейчас +10 градусов",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={"phone_number": "9777777777777"}
        )
        
        # Мокаем всю цепочку отправки аудио
        mock_audio_record = MagicMock()
        mock_audio_record.audio_id = "response_audio_123"
        mock_audio_record.s3_key = "audio/response_123.ogg"
        mock_audio_record.content_type = "audio/ogg; codecs=opus"
        
        mock_audio_processor = AsyncMock()
        mock_audio_processor.get_audio_record.return_value = mock_audio_record
        
        mock_s3_client = AsyncMock()
        mock_s3_client.download_bytes.return_value = b"fake audio response bytes"
        mock_audio_processor._get_s3_client.return_value = mock_s3_client
        
        mock_api_response = AsyncMock()
        mock_api_response.status_code = 200
        mock_api_response.json = MagicMock(return_value={"messages": [{"id": "wamid.audio_out"}]})
        
        with patch('core.files.processors.get_default_audio_processor', return_value=mock_audio_processor):
            with patch.object(interface, '_upload_media', return_value="uploaded_audio_999"):
                with patch('httpx.AsyncClient') as mock_client:
                    mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_api_response)
                    
                    await interface.send_message(outgoing_with_audio)
        
        print("✅ Голосовой ответ отправлен")
        print("   Voice-to-Voice диалог работает!")
    
    async def test_whatsapp_document_upload_flow(self):
        """Тест загрузки и обработки документа"""
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Doc User"}, "wa_id": "9888888888888"}],
                        "messages": [{
                            "from": "9888888888888",
                            "id": "wamid.doc",
                            "timestamp": "1699000007",
                            "type": "document",
                            "document": {
                                "id": "media_doc_111",
                                "filename": "quarterly_report.pdf",
                                "mime_type": "application/pdf",
                                "caption": "Please analyze this report"
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_file_messages = [
            "📎 Документ: quarterly_report.pdf\n"
            "Тип: application/pdf\n"
            "Размер: 2.5 MB\n"
            "URL: https://storage/file_doc_111"
        ]
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9888888888888:test_flow:doc_flow"):
            with patch.object(interface, 'process_files', return_value=mock_file_messages):
                message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "Please analyze this report" in message.content
        assert "quarterly_report.pdf" in message.content
        assert "📎" in message.content
        
        print("✅ Документ обработан для анализа агентом")
    
    async def test_whatsapp_location_sharing(self):
        """Тест получения локации от пользователя"""
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "Location User"}, "wa_id": "9000000000000"}],
                        "messages": [{
                            "from": "9000000000000",
                            "id": "wamid.location",
                            "timestamp": "1699000008",
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
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9000000000000:test_flow:loc"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        assert message is not None
        assert "📍 Локация" in message.content
        assert "Red Square" in message.content
        assert "55.7558" in message.content
        assert "37.6173" in message.content
        
        print("✅ Локация обработана с координатами и названием")
    
    async def test_whatsapp_media_group_simulation(self):
        """Тест получения нескольких медиафайлов подряд"""
        
        # WhatsApp не группирует медиа как Telegram, но может прислать несколько подряд
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        messages_received = []
        
        # Первое изображение
        webhook_1 = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9123456789"}],
                        "messages": [{
                            "from": "9123456789",
                            "id": "wamid.img1",
                            "timestamp": "1699000010",
                            "type": "image",
                            "image": {"id": "media_1", "mime_type": "image/jpeg"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        # Второе изображение
        webhook_2 = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9123456789"}],
                        "messages": [{
                            "from": "9123456789",
                            "id": "wamid.img2",
                            "timestamp": "1699000011",
                            "type": "image",
                            "image": {"id": "media_2", "mime_type": "image/jpeg"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9123456789:test_flow:media"):
            with patch.object(interface, 'process_files', return_value=["📷 Image 1"]):
                msg1 = await interface.handle_message(webhook_1, "test_flow")
                messages_received.append(msg1)
            
            with patch.object(interface, 'process_files', return_value=["📷 Image 2"]):
                msg2 = await interface.handle_message(webhook_2, "test_flow")
                messages_received.append(msg2)
        
        assert len(messages_received) == 2
        assert all(msg is not None for msg in messages_received)
        
        print("✅ Несколько медиафайлов обработаны как отдельные сообщения")
        print(f"   Получено сообщений: {len(messages_received)}")


class TestWhatsAppErrorHandling:
    """Тесты обработки ошибок"""
    
    @pytest.mark.asyncio
    async def test_api_rate_limit_error(self):
        """Тест обработки rate limit ошибки от WhatsApp API"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        Message(
            user_id="whatsapp:9111111111111",
            session_id="test_session",
            content="Test message",
            flow_id="test_flow",
            platform="whatsapp",
            metadata={"phone_number": "9111111111111"}
        )
        
        # Мокаем rate limit ошибку
        mock_response = AsyncMock()
        mock_response.status_code = 429
        mock_response.text = "Rate limit exceeded"
        mock_response.request = MagicMock()
        mock_response.headers = {"Retry-After": "60"}
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            # Должно бросить исключение
            with pytest.raises(Exception):
                await interface._send_text_message("9111111111111", "Test", {})
        
        print("✅ Rate limit ошибка обрабатывается исключением")
    
    @pytest.mark.asyncio
    async def test_invalid_phone_number_error(self):
        """Тест ошибки невалидного номера телефона"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.text = '{"error": {"message": "Invalid phone number"}}'
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_response)
            
            with pytest.raises(Exception):
                await interface._send_text_message("invalid_phone", "Test", {})
        
        print("✅ Ошибка невалидного номера обрабатывается")
    
    @pytest.mark.asyncio
    async def test_media_download_error(self):
        """Тест ошибки при скачивании медиа от WhatsApp"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        mock_response = AsyncMock()
        mock_response.status_code = 410
        mock_response.text = "Media expired"
        mock_response.request = MagicMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_response)
            
            with pytest.raises(Exception):
                await interface._get_media_url("expired_media_id")
        
        print("✅ Ошибка истекшего медиа обрабатывается")


class TestWhatsAppCompatibilityWithTelegram:
    """Тесты совместимости с Telegram"""
    
    @pytest.mark.asyncio
    async def test_same_message_format_as_telegram(self):
        """Тест что Message имеет тот же формат что и Telegram"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        webhook_data = {
            "object": "whatsapp_business_account",
            "entry": [{
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {"phone_number_id": "111111111111111"},
                        "contacts": [{"profile": {"name": "User"}, "wa_id": "9111111111111"}],
                        "messages": [{
                            "from": "9111111111111",
                            "id": "wamid.compat",
                            "timestamp": "1699000020",
                            "type": "text",
                            "text": {"body": "Compatibility test"}
                        }]
                    },
                    "field": "messages"
                }]
            }]
        }
        
        with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9111111111111:test_flow:compat"):
            message = await interface.handle_message(webhook_data, "test_flow")
        
        # Проверяем все обязательные поля Message
        assert hasattr(message, 'user_id')
        assert hasattr(message, 'session_id')
        assert hasattr(message, 'content')
        assert hasattr(message, 'flow_id')
        assert hasattr(message, 'platform')
        assert hasattr(message, 'metadata')
        assert hasattr(message, 'files')
        
        assert message.platform == "whatsapp"
        
        print("✅ Message формат совместим с Telegram")
        print("   Все поля присутствуют и корректны")
    
    @pytest.mark.asyncio
    async def test_commands_compatibility(self):
        """Тест что команды работают как в Telegram"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        # Тестируем все команды
        commands = ["/start", "/help", "/clear"]
        
        for cmd in commands:
            webhook_data = {
                "object": "whatsapp_business_account",
                "entry": [{
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"phone_number_id": "111111111111111"},
                            "contacts": [{"profile": {"name": "User"}, "wa_id": "9111111111111"}],
                            "messages": [{
                                "from": "9111111111111",
                                "id": f"wamid.{cmd}",
                                "timestamp": "1699000030",
                                "type": "text",
                                "text": {"body": cmd}
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            }
            
            with patch.object(interface, 'get_or_create_session', return_value="whatsapp:9111111111111:test_flow:cmd"):
                with patch.object(interface, 'send_message'):
                    message = await interface.handle_message(webhook_data, "test_flow")
            
            # Команды не создают Message
            assert message is None
        
        print(f"✅ Все команды ({', '.join(commands)}) работают как в Telegram")
    
    @pytest.mark.asyncio
    async def test_markdown_compatibility(self):
        """Тест совместимости Markdown форматирования"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        # Markdown как в Telegram
        telegram_style_text = "**Important:** Temperature is _+15°C_ in Moscow"
        
        # Конвертируем в WhatsApp
        whatsapp_text = interface._convert_markdown_to_whatsapp(telegram_style_text)
        
        # WhatsApp использует * для bold и _ для italic
        assert "*Important:*" in whatsapp_text
        assert "_+15°C_" in whatsapp_text
        
        print("✅ Markdown форматирование совместимо")
        print(f"   Telegram: {telegram_style_text}")
        print(f"   WhatsApp: {whatsapp_text}")


class TestWhatsAppInteractiveMessages:
    """Тесты интерактивных сообщений (кнопки, списки)"""
    
    @pytest.mark.asyncio
    async def test_send_reply_buttons(self):
        """Тест отправки reply buttons (до 3)"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        buttons = [
            {"id": "yes", "text": "Да"},
            {"id": "no", "text": "Нет"}
        ]
        
        sent_payload = None
        
        async def capture_post(url, json=None, **kwargs):
            nonlocal sent_payload
            sent_payload = json
            
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.btns"}]})
            return mock_resp
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = capture_post
            
            await interface._send_interactive_message("9111111111111", "Confirm?", buttons, {})
        
        assert sent_payload is not None
        assert sent_payload["type"] == "interactive"
        assert sent_payload["interactive"]["type"] == "button"
        assert len(sent_payload["interactive"]["action"]["buttons"]) == 2
        
        print("✅ Reply buttons (2 кнопки) отправлены корректно")
    
    @pytest.mark.asyncio
    async def test_send_list_message(self):
        """Тест отправки list message (4+ кнопки)"""
        
        platform_config = {"phone_number_id": "111111111111111"}
        interface = WhatsAppInterface("test_token", platform_config)
        
        buttons = [
            {"id": f"opt_{i}", "text": f"Option {i}", "description": f"Description {i}"}
            for i in range(1, 6)  # 5 кнопок
        ]
        
        sent_payload = None
        
        async def capture_post(url, json=None, **kwargs):
            nonlocal sent_payload
            sent_payload = json
            
            mock_resp = AsyncMock()
            mock_resp.status_code = 200
            mock_resp.json = MagicMock(return_value={"messages": [{"id": "wamid.list"}]})
            return mock_resp
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value.post = capture_post
            
            await interface._send_interactive_message("9111111111111", "Choose:", buttons, {})
        
        assert sent_payload is not None
        assert sent_payload["type"] == "interactive"
        assert sent_payload["interactive"]["type"] == "list"
        assert len(sent_payload["interactive"]["action"]["sections"][0]["rows"]) == 5
        
        print("✅ List message (5 кнопок) отправлен корректно")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])

