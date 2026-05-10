"""
Точка входа для CRM Worker.

Запуск: taskiq worker apps.crm_worker.worker:worker_app
"""

from core.config import set_settings
from core.config.loader import load_merged_config

from apps.crm.config import CRMSettings
from core.tasks.logging_init import setup_worker_logging_early

_merged_crm = load_merged_config(service_name="crm", silent=True)
_crm_worker_settings = CRMSettings(**_merged_crm)
setup_worker_logging_early("crm_worker", logging_config=_crm_worker_settings.logging)
set_settings(_crm_worker_settings)

from apps.crm_worker.broker import broker as worker_app

import apps.crm_worker.tasks.analysis_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.reembed_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.namespace_integration_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.daily_summary_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.knowledge_import_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.note_markdown_tasks  # noqa: F401, E402

__all__ = ["worker_app"]
