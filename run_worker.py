#!/usr/bin/env python3
"""
Запуск воркера для обработки задач.
"""

import asyncio
from app.core.logger import setup_worker_logging, get_logger
from app.workers.task_processor import main

# Настройка логирования
setup_worker_logging()
logger = get_logger(__name__)

if __name__ == "__main__":
    logger.info("🔄 Запуск Task Processor...")
    asyncio.run(main())
