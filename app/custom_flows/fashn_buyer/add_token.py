"""
Скрипт для добавления токена бота в БД.
"""

import asyncio
import json
import logging
from app.db.repositories import Storage

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def add_bot_token():
    """Добавляет токен бота fashn_agents_lab_test_bot в БД"""
    
    storage = Storage()
    
    # Данные бота
    username = "fashn_agents_lab_test_bot"
    token = "8395450365:AAHSUMIRKYfQpKEhuPtUJq84eZpjIRwKljo"
    
    # Ключ для сохранения
    token_key = f"token:telegram:{username}"
    
    try:
        # Сохраняем токен как JSON в глобальном контексте
        await storage.set(token_key, json.dumps(token), force_global=True)
        
        logger.info(f"✅ Токен добавлен в БД: {token_key}")
        logger.info(f"🤖 Бот: @{username}")
        
        # Проверяем что токен сохранился
        saved_token = await storage.get(token_key, force_global=True)
        if saved_token:
            logger.info("✅ Токен успешно сохранен и проверен")
        else:
            logger.error("❌ Ошибка: токен не найден после сохранения")
            
    except Exception as e:
        logger.error(f"❌ Ошибка добавления токена: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(add_bot_token())
