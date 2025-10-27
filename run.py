#!/usr/bin/env python3
"""
Простой скрипт запуска Agents Lab.
"""

import uvicorn
from app.core.config import settings

if __name__ == "__main__":
    print("🚀 Запуск Agents Lab...")
    print(f"📍 Адрес: http://{settings.server.host}:{settings.server.port}")
    print(f"🔧 Debug режим: {settings.server.debug}")

    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",  # Всегда используем INFO уровень, детальные настройки в main.py
    )
