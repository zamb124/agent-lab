"""
Точка входа для TaskIQ flows worker.

Запуск: taskiq worker apps.flows_worker.worker:worker_app

Этот модуль:
1. Инициализирует settings сервисов
2. Импортирует worker app из apps.flows_worker.broker
3. Регистрирует startup/shutdown события
4. Регистрирует tasks всех сервисов
"""

from apps.flows.config import get_settings

get_settings()

from apps.flows_worker.broker import broker as worker_app

import apps.flows.src.tasks.company_init_tasks  # noqa: F401
import apps.flows.src.tasks.eval_task  # noqa: F401
import apps.flows.src.tasks.flow_tasks  # noqa: F401
import apps.flows.src.tasks.llm_tasks  # noqa: F401
import apps.flows.src.tasks.node_tasks  # noqa: F401
import apps.flows.src.tasks.scheduled_tasks  # noqa: F401
import apps.flows.src.tasks.tool_tasks  # noqa: F401

# CRM attachment tasks теперь в rag worker (apps/rag_worker/worker.py)
# import apps.crm.tasks.attachment_tasks  # noqa: F401

__all__ = ["worker_app"]
