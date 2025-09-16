#!/usr/bin/env python3
"""
Отладочный скрипт для тестирования создания и обработки задач
"""
import asyncio
import json
import logging
from datetime import datetime, timezone

from app.core.storage import Storage
from app.core.models import TaskConfig, TaskStatus
from app.workers.task_processor import TaskProcessor

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def create_test_task():
    """Создает тестовую задачу"""
    storage = Storage()
    
    task_config = TaskConfig(
        task_id="debug_task_003",
        flow_id="test_flow",
        user_id="debug_user",
        session_id="debug_session",
        platform="telegram",
        status=TaskStatus.PENDING,
        input_data={
            "message": "Привет! Это тестовое сообщение",
            "metadata": {
                "chat_id": "94434940",  # Реальный chat_id из логов
                "bot_username": "agents_lab_bot"
            }
        },
        created_at=datetime.now(timezone.utc).isoformat()
    )
    
    await storage.set(f"task:{task_config.task_id}", task_config.model_dump_json())
    logger.info(f"✅ Создана тестовая задача: {task_config.task_id}")
    
    return task_config


async def process_test_task():
    """Обрабатывает одну задачу"""
    processor = TaskProcessor()
    
    # Обрабатываем pending задачи
    await processor._process_pending_tasks()


async def check_task_result(task_id: str):
    """Проверяет результат задачи"""
    storage = Storage()
    
    task_json = await storage.get(f"task:{task_id}")
    if task_json:
        task_data = json.loads(task_json)
        logger.info(f"📋 Статус задачи {task_id}: {task_data['status']}")
        
        if task_data.get('error_message'):
            logger.error(f"❌ Ошибка: {task_data['error_message']}")
        
        if task_data.get('output_data'):
            logger.info(f"📤 Результат: {task_data['output_data']}")
    else:
        logger.error(f"❌ Задача {task_id} не найдена")


async def main():
    """Главная функция отладки"""
    logger.info("🔍 Начинаем отладку задач...")
    
    try:
        # 1. Создаем тестовую задачу
        logger.info("1. Создание тестовой задачи...")
        task = await create_test_task()
        
        # 2. Обрабатываем задачу
        logger.info("2. Обработка задачи...")
        await process_test_task()
        
        # 3. Проверяем результат
        logger.info("3. Проверка результата...")
        await check_task_result(task.task_id)
        
    except Exception as e:
        logger.error(f"❌ Ошибка отладки: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())
