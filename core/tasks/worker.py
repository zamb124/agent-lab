"""
Точка входа для TaskIQ воркера и планировщика.

Запуск воркера:
    taskiq worker core.tasks.worker:broker
    taskiq worker core.tasks.worker:broker --workers 4
    taskiq worker core.tasks.worker:broker --reload  # для разработки

Запуск планировщика (для отложенных задач):
    taskiq scheduler core.tasks.worker:scheduler
    taskiq scheduler core.tasks.worker:scheduler --reload
"""

from core.tasks.broker import broker, scheduler, schedule_source

# Импортируем ВСЕ задачи чтобы они зарегистрировались в брокере
import apps.agents.tasks.agent_tasks  # noqa: F401
import apps.agents.tasks.message_tasks  # noqa: F401
import apps.agents.tasks.company_tasks  # noqa: F401
import apps.frontend.tasks.notification_tasks  # noqa: F401
import apps.agents.services.migration.migrator  # noqa: F401 - migrate_company_defaults

# Экспортируем для taskiq CLI
__all__ = ["broker", "scheduler", "schedule_source"]
