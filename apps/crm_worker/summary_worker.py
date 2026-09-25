"""CRM summary worker (очередь ``crm_summary``).

Запуск: taskiq worker apps.crm_worker.summary_worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.crm.config import CRMSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_crm_summary_worker_settings = CRMSettings.model_validate(
    load_merged_config(service_name="crm", silent=True)
)
setup_worker_logging_early("crm_summary_worker", logging_config=_crm_summary_worker_settings.logging)
set_settings(_crm_summary_worker_settings)
set_files_route_segment(resolve_files_route_segment("crm_summary_worker"))

import importlib

from apps.crm_worker.di import CrmWorkerDi
from apps.worker_manifest import wire_worker
from core.tasks.worker_bootstrap import build_worker

_ = importlib.import_module("apps.crm.events")

broker = wire_worker("crm_summary")
worker_app = build_worker(
    broker,
    service_name="crm_summary_worker",
    queue="crm_summary",
    settings=_crm_summary_worker_settings,
    di_class=CrmWorkerDi,
    database="crm_url",
)

__all__ = ["worker_app"]
