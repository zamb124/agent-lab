"""
Точка входа для TaskIQ scheduler.

Запуск: taskiq scheduler apps.scheduler.scheduler:scheduler
"""

from apps.agents.config import get_settings
from core.scheduler.scheduler import create_scheduler

settings = get_settings()
scheduler = create_scheduler(settings.database.redis_url)

# Импортируем tasks чтобы scheduler знал о них
import apps.agents.src.tasks.agent_tasks  # noqa: F401, E402
import apps.agents.src.tasks.eval_task  # noqa: F401, E402
import apps.agents.src.tasks.tool_tasks  # noqa: F401, E402
import apps.agents.src.tasks.push_notification_tasks  # noqa: F401, E402
import apps.agents.src.tasks.scheduled_tasks  # noqa: F401, E402

__all__ = ["scheduler"]

