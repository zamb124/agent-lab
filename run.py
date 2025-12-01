#!/usr/bin/env python3
"""
Простой скрипт запуска Humanitec.
"""

import uvicorn
from apps.agents.config import get_agents_settings

if __name__ == "__main__":
    settings = get_agents_settings()
    print("🚀 Запуск Humanitec...")
    print(f"📍 Адрес: http://{settings.server.host}:{settings.server.port}")
    print(f"🔧 Debug режим: {settings.server.debug}")

    uvicorn.run(
        "apps.agents.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        log_level="info",
    )
