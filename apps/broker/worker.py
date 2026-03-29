"""
Точка входа для TaskIQ worker платформы.

Запуск: taskiq worker apps.broker.worker:broker

Этот модуль:
1. Инициализирует settings сервисов
2. Импортирует broker из apps.broker.broker
3. Регистрирует startup/shutdown события
4. Регистрирует tasks всех сервисов
"""

# Инициализируем settings (agents)
from apps.flows.config import get_settings
get_settings()

# Импортируем broker из apps.broker.broker
from apps.broker.broker import broker

# Регистрируем tasks сервиса agents
import apps.flows.src.tasks.flow_tasks  # noqa: F401
import apps.flows.src.tasks.eval_task  # noqa: F401
import apps.flows.src.tasks.node_tasks  # noqa: F401
import apps.flows.src.tasks.tool_tasks  # noqa: F401
import apps.flows.src.tasks.push_notification_tasks  # noqa: F401
import apps.flows.src.tasks.scheduled_tasks  # noqa: F401
import apps.flows.src.tasks.company_init_tasks  # noqa: F401
import apps.flows.src.tasks.llm_models_tasks  # noqa: F401
import apps.flows.src.tasks.calendar_sync_tasks  # noqa: F401

# CRM attachment tasks теперь в rag broker (apps/rag_worker/worker.py)
# import apps.crm.tasks.attachment_tasks  # noqa: F401

# Экспортируем объекты для taskiq CLI
__all__ = ["broker"]

