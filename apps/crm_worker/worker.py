"""
Точка входа для CRM Worker.

Запуск: taskiq worker apps.crm_worker.worker:broker
"""

from core.config import set_settings
from core.config.loader import load_merged_config

from apps.crm.config import CRMSettings

set_settings(CRMSettings(**load_merged_config(service_name="crm")))

from apps.crm_worker.broker import broker

import apps.crm_worker.tasks.daily_summary_tasks  # noqa: F401, E402

__all__ = ["broker"]
