"""
Тестовый скрипт для проверки поиска файлов по ID.
"""

import asyncio
import json
import logging
from app.core.storage import Storage
from app.core.file_processor import get_default_file_processor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_file_search():
    """Тестирует поиск файлов по различным ID"""
    
    # Тестовые file_id из логов
    test_file_ids = [
        "file_c7061c82aa4e",
        "file_189ad8c09bdc", 
        "file_dc7c0ce28d6d",
        "file_4e33c8955ada"
    ]
    
    storage = Storage()
    file_processor = await get_default_file_processor()
    
    for file_id in test_file_ids:
        logger.info(f"\n🔍 Тестируем поиск файла: {file_id}")
        
        # 1. Пробуем через FileProcessor
        try:
            file_record = await file_processor.get_file_record(file_id)
            if file_record:
                logger.info(f"✅ FileProcessor нашел файл: {file_record.original_name}")
            else:
                logger.info("❌ FileProcessor НЕ нашел файл")
        except Exception as e:
            logger.error(f"❌ Ошибка FileProcessor: {e}")
        
        # 2. Пробуем разные ключи в Storage
        possible_keys = [
            file_id,
            f"s3:vkcloud:{file_id}",
            f"company:system:s3:vkcloud:{file_id}",
            f"file:{file_id}",
        ]
        
        for key in possible_keys:
            try:
                data = await storage.get(key)
                if data:
                    logger.info(f"✅ Storage нашел по ключу: {key}")
                    if isinstance(data, str):
                        file_info = json.loads(data)
                        logger.info(f"   Файл: {file_info.get('original_name', 'unknown')}")
                    break
                else:
                    logger.info(f"❌ Storage НЕ нашел по ключу: {key}")
            except Exception as e:
                logger.error(f"❌ Ошибка поиска по ключу {key}: {e}")
        
        # 3. Пробуем поиск по префиксу
        try:
            logger.info(f"🔍 Ищем все ключи содержащие {file_id}...")
            all_keys = await storage.list_by_prefix("", 1000, force_global=True)
            matching_keys = [key for key in all_keys if file_id in key]
            if matching_keys:
                logger.info(f"✅ Найдены ключи с {file_id}: {matching_keys}")
            else:
                logger.info(f"❌ Не найдено ключей содержащих {file_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка поиска по префиксу: {e}")


if __name__ == "__main__":
    asyncio.run(test_file_search())
