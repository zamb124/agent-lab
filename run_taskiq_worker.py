#!/usr/bin/env python3
"""
Запуск TaskIQ воркера для обработки задач.

Использование:
    python run_taskiq_worker.py
    
Или через taskiq CLI:
    taskiq worker core.tasks.worker:broker --workers 4
"""

import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.logging import setup_logging, get_logger
from apps.agents.config import get_agents_settings


async def run_worker():
    """Запуск TaskIQ воркера"""
    from core.tasks.broker import broker
    
    # Импортируем все задачи для регистрации
    import apps.agents.tasks.agent_tasks  # noqa: F401
    import apps.agents.tasks.message_tasks  # noqa: F401
    import apps.frontend.tasks.notification_tasks  # noqa: F401
    
    logger = get_logger(__name__)
    logger.info("Запуск TaskIQ воркера...")
    
    # Запускаем воркер
    await broker.startup()
    
    try:
        # Слушаем задачи
        await broker.listen()
    finally:
        await broker.shutdown()


if __name__ == "__main__":
    settings = get_agents_settings()
    setup_logging("worker", settings.logging)
    logger = get_logger(__name__)
    
    logger.info("TaskIQ Worker starting...")
    asyncio.run(run_worker())

