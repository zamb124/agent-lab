"""
Тесты интеграции файловой системы.
"""
import pytest

from core.files.processors import FileProcessor
from apps.agents.interfaces.telegram_interface import TelegramInterface


@pytest.mark.asyncio
class TestFileIntegration:
    """Тесты файловой интеграции"""
    
    @pytest.mark.skip(reason="Нестабилен при массовом запуске")
    async def test_file_processor_basic(self, migrated_db):
        """Базовый тест файлового процессора"""
        from apps.agents.container import get_agents_container
        file_repository = get_agents_container().file_repository
        processor = FileProcessor(file_repository=file_repository)
        
        test_data = b"Test file content for integration"
        
        try:
            file_record = await processor.process_file_from_bytes(
                data=test_data,
                original_name="test-integration.txt",
                uploaded_by="test_user",
                metadata={"source": "integration_test"},
                tags=["test", "integration"]
            )
            
            # Проверяем что запись создана правильно
            assert file_record.file_id.startswith("file_")
            assert file_record.provider == "vkcloud"  # Из конфигурации
            assert file_record.original_name == "test-integration.txt"
            assert file_record.s3_bucket == "vkbucket"
            assert file_record.key.startswith("s3:vkcloud:")
            
            # URL должен быть на платформу (для контроля доступа)
            assert file_record.url is not None
            assert "/api/v1/files/download/" in file_record.url
            assert file_record.file_id in file_record.url
            
            # Прямой S3 URL должен содержать endpoint
            assert file_record.direct_s3_url is not None
            assert "hb.ru-msk.vkcloud-storage.ru" in file_record.direct_s3_url
            
            # Проверяем форматирование сообщения
            message = processor.format_file_message(file_record)
            assert "📎 Файл:" in message or "[FILE]" in message
            assert file_record.file_id in message
            assert file_record.original_name in message
            assert file_record.url in message
            
            print(f"✅ Файл обработан: {file_record.key}")
            print(f"✅ Статус: {file_record.status}")
            print(f"✅ URL: {file_record.url}")
            
        finally:
            await processor.close()
    
    async def test_telegram_file_extraction(self):
        """Тест извлечения файлов из Telegram сообщений"""
        interface = TelegramInterface("test_token", {"username": "test_bot"})
        
        # Тест с документом
        document_message = {
            "message_id": 123,
            "from": {"id": 12345},
            "chat": {"id": 12345},
            "text": "Вот документ",
            "document": {
                "file_id": "BAADBAADrwADBREAAcbKAeJyqJoGAg",
                "file_name": "important_document.pdf",
                "file_size": 54321,
                "mime_type": "application/pdf"
            }
        }
        
        files_data = await interface._extract_files_from_message(document_message)
        
        assert len(files_data) == 1
        file_info = files_data[0]
        assert file_info["type"] == "document"
        assert file_info["file_name"] == "important_document.pdf"
        assert file_info["file_size"] == 54321
        assert file_info["mime_type"] == "application/pdf"
        
        print(f"✅ Документ извлечен: {file_info['file_name']}")
        
        # Тест с фото (выбор самого большого)
        photo_message = {
            "message_id": 124,
            "from": {"id": 12345},
            "chat": {"id": 12345},
            "text": "Красивое фото",
            "photo": [
                {"file_id": "photo_small", "file_size": 1000},
                {"file_id": "photo_large", "file_size": 10000},
                {"file_id": "photo_medium", "file_size": 5000}
            ]
        }
        
        photo_files = await interface._extract_files_from_message(photo_message)
        
        assert len(photo_files) == 1
        photo_info = photo_files[0]
        assert photo_info["file_id"] == "photo_large"  # Самое большое
        assert photo_info["file_size"] == 10000
        
        print(f"✅ Фото извлечено: {photo_info['file_id']} (размер: {photo_info['file_size']})")
        
        # Тест с несколькими типами файлов
        multi_message = {
            "message_id": 125,
            "from": {"id": 12345},
            "chat": {"id": 12345},
            "text": "Много файлов",
            "document": {
                "file_id": "doc_123",
                "file_name": "doc.pdf",
                "file_size": 1000
            },
            "voice": {
                "file_id": "voice_456",
                "file_size": 2000,
                "mime_type": "audio/ogg"
            }
        }
        
        multi_files = await interface._extract_files_from_message(multi_message)
        
        assert len(multi_files) == 2
        file_types = [f["type"] for f in multi_files]
        assert "document" in file_types
        assert "voice" in file_types
        
        print(f"✅ Множественные файлы: {file_types}")
    
    async def test_file_message_parsing(self):
        """Тест парсинга информации о файлах из сообщений"""
        # Создаем тестовое сообщение с файлом
        file_message = (
            "[FILE]\n"
            "📎 Файл: test-document.pdf "
            "(ID: file_abc123, URL: https://storage.yandexcloud.net/bucket/file.pdf, "
            "тип: application/pdf, размер: 1.5 MB)\n"
            "[/FILE]"
        )
        
        extracted = FileProcessor.extract_file_info_from_message(file_message)
        
        assert len(extracted) == 1
        file_info = extracted[0]
        assert file_info["name"] == "test-document.pdf"
        assert file_info["file_id"] == "file_abc123"
        assert file_info["url"] == "https://storage.yandexcloud.net/bucket/file.pdf"
        assert file_info["content_type"] == "application/pdf"
        assert file_info["size"] == "1.5 MB"
        
        print(f"✅ Информация о файле извлечена: {file_info['name']}")
        
        # Тест с множественными файлами в сообщении
        multi_file_message = (
            "Вот файлы:\n\n"
            "[FILE]\n"
            "📎 Файл: doc1.pdf (ID: file_001, URL: https://example.com/doc1.pdf, тип: application/pdf, размер: 100 байт)\n"
            "[/FILE]\n\n"
            "И еще один:\n\n"
            "[FILE]\n"
            "📎 Файл: image.jpg (ID: file_002, URL: https://example.com/image.jpg, тип: image/jpeg, размер: 2.3 MB)\n"
            "[/FILE]"
        )
        
        multi_extracted = FileProcessor.extract_file_info_from_message(multi_file_message)
        
        assert len(multi_extracted) == 2
        assert multi_extracted[0]["name"] == "doc1.pdf"
        assert multi_extracted[1]["name"] == "image.jpg"
        
        print(f"✅ Множественные файлы извлечены: {len(multi_extracted)} файлов")
