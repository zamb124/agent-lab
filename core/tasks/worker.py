"""
Точка входа для TaskIQ воркера.

Запуск:
    taskiq worker core.tasks.worker:broker
    taskiq worker core.tasks.worker:broker --workers 4
    taskiq worker core.tasks.worker:broker --reload  # для разработки
"""

from core.tasks.broker import broker

# Импортируем ВСЕ задачи чтобы они зарегистрировались в брокере
import apps.agents.tasks.agent_tasks  # noqa: F401
import apps.agents.tasks.message_tasks  # noqa: F401
import apps.frontend.tasks.notification_tasks  # noqa: F401

# broker экспортируется для taskiq CLI
__all__ = ["broker"]

