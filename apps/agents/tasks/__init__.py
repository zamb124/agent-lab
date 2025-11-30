"""
TaskIQ задачи для сервиса agents.

- process_agent_task: обработка сообщения агентом
- send_message_task: отправка сообщения через интерфейс
"""

from apps.agents.tasks.agent_tasks import process_agent_task
from apps.agents.tasks.message_tasks import send_message_task

__all__ = ["process_agent_task", "send_message_task"]

