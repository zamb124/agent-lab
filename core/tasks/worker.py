"""
Точка входа для TaskIQ воркера и планировщика.

Запуск воркера (базовый, без задач приложений):
    taskiq worker core.tasks.worker:broker

Для запуска с задачами приложений используйте apps.worker:broker

"""

from core.tasks.broker import broker, scheduler, schedule_source

# Импортируем ВСЕ задачи чтобы они зарегистрировались в брокере


# Экспортируем для taskiq CLI
__all__ = ["broker", "scheduler", "schedule_source"]
