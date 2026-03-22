"""
Точка входа для TaskIQ scheduler.

Запуск: taskiq scheduler apps.scheduler.scheduler:scheduler
"""

from apps.flows.config import get_settings
from core.scheduler.scheduler import create_scheduler

settings = get_settings()
scheduler = create_scheduler(settings.database.redis_url)

# Импортируем tasks чтобы scheduler знал о них
import apps.flows.src.tasks.flow_tasks  # noqa: F401, E402
import apps.flows.src.tasks.eval_task  # noqa: F401, E402
import apps.flows.src.tasks.tool_tasks  # noqa: F401, E402
import apps.flows.src.tasks.push_notification_tasks  # noqa: F401, E402
import apps.flows.src.tasks.scheduled_tasks  # noqa: F401, E402

__all__ = ["scheduler"]

