"""
Точка входа для CRM Worker.

Запуск: taskiq worker apps.crm_worker.worker:worker_app
"""

from core.config import set_settings
from core.config.loader import load_merged_config

from apps.crm.config import CRMSettings

set_settings(CRMSettings(**load_merged_config(service_name="crm")))

from apps.crm_worker.broker import broker as worker_app

import apps.crm_worker.tasks.analysis_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.daily_summary_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.knowledge_import_tasks  # noqa: F401, E402

__all__ = ["worker_app"]
