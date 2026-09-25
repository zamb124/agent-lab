"""
Точка входа для TaskIQ scheduler.

Запуск: taskiq scheduler apps.scheduler.scheduler:scheduler
"""

from apps.scheduler.config import get_scheduler_settings
from apps.scheduler.dispatch import create_scheduler, require_scheduled_tasks_registered
from apps.worker_manifest import wire_all
from core.logging.setup import setup_logging

settings = get_scheduler_settings()
setup_logging(service_name="scheduler", logging_config=settings.logging)

wire_all()
require_scheduled_tasks_registered()

# Schedules живут в том же Redis, что TaskIQ broker (не database.redis_url).
scheduler = create_scheduler(settings.tasks.broker_url)

__all__ = ["scheduler"]
