"""
Точка входа для Idle Worker.

Запуск: taskiq worker apps.idle_worker.worker:worker_app
"""

from apps.flows.config import FlowSettings, set_settings as set_flow_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_flows = load_merged_config(service_name="flows", silent=True)
_idle_worker_flow_settings = FlowSettings(**_merged_flows)
setup_worker_logging_early("idle_worker", logging_config=_idle_worker_flow_settings.logging)
set_flow_settings(_idle_worker_flow_settings)

from apps.idle_worker.broker import broker as worker_app

import apps.idle_worker.tasks.calendar_sync_tasks  # noqa: F401
import apps.idle_worker.tasks.llm_models_tasks  # noqa: F401
import apps.idle_worker.tasks.push_notification_tasks  # noqa: F401
import apps.idle_worker.tasks.payment_sync_tasks  # noqa: F401
import apps.idle_worker.tasks.span_billing_settlement_tasks  # noqa: F401

__all__ = ["worker_app"]
