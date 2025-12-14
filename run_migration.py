#!/usr/bin/env python3
"""
Скрипт для ручного запуска миграции системной компании.
Создает системную компанию и мигрирует всех агентов, flows и tools.
"""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent))

from core.logging import setup_logging
from apps.agents.config import get_agents_settings
from apps.agents.container import get_agents_container
from core.files import initialize_default_processors

async def run_migration():
    """Запускает миграцию системной компании"""

    # Загружаем настройки
    settings = get_agents_settings()

    # Настройка логирования
    setup_logging("migration", settings.logging)

    print("🚀 Запуск миграции системной компании...\n")

    # Получаем контейнер
    container = get_agents_container()

    # Инициализируем файловые процессоры
    initialize_default_processors(
        file_repository=container.file_repository,
        storage=container.storage
    )

    # Запускаем миграцию
    migrator = container.migrator
    try:
        await migrator.run_full_migration()
        print("\n✅ Миграция завершена успешно!")
    except Exception as e:
        print(f"\n❌ Ошибка при миграции: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_migration())

