#!/usr/bin/env python3
"""
Запуск воркера для обработки задач.
"""

import asyncio
import logging
from app.workers.task_processor import main

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

if __name__ == "__main__":
    print("🔄 Запуск Task Processor...")
    asyncio.run(main())
