"""
Точка входа для Idle Worker.

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

from apps.flows.config import get_settings

get_settings()

from apps.idle_worker.broker import broker as worker_app

import apps.idle_worker.tasks.calendar_sync_tasks  # noqa: F401
import apps.idle_worker.tasks.llm_models_tasks  # noqa: F401
import apps.idle_worker.tasks.push_notification_tasks  # noqa: F401
import apps.idle_worker.tasks.span_billing_settlement_tasks  # noqa: F401

__all__ = ["worker_app"]
