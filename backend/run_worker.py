#!/usr/bin/env python3
"""
Запуск воркера для обработки задач.
"""

import asyncio
from app.workers.task_processor import main

if __name__ == "__main__":
    print("🔄 Запуск Task Processor...")
    asyncio.run(main())
