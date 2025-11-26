#!/usr/bin/env python3
"""
Запуск воркера для обработки задач.
"""

import asyncio
from core.logging import setup_logging, get_logger
from apps.agents.config import get_agents_settings
from apps.agents.workers.task_processor import main

if __name__ == "__main__":
    settings = get_agents_settings()
    setup_logging("agents", settings.logging)
    logger = get_logger(__name__)
    
    logger.info("🔄 Запуск Task Processor...")
    asyncio.run(main())
