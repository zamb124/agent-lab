"""CRM Worker (очередь ``crm``).

Запуск: taskiq worker apps.crm_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.crm.config import CRMSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.files.urls import resolve_files_route_segment, set_files_route_segment
from core.tasks.logging_init import setup_worker_logging_early

_crm_worker_settings = CRMSettings.model_validate(load_merged_config(service_name="crm", silent=True))
setup_worker_logging_early("crm_worker", logging_config=_crm_worker_settings.logging)
set_settings(_crm_worker_settings)
set_files_route_segment(resolve_files_route_segment("crm_worker"))

import importlib

from apps.crm.services.task_service import TaskService
from apps.crm_worker.di import CrmWorkerDi
from apps.worker_manifest import wire_worker
from core.di import recipe
from core.logging import get_logger
from core.tasks.worker_bootstrap import build_worker

logger = get_logger(__name__)

_ = importlib.import_module("apps.crm.events")


async def reconcile_crm_worker_tasks(task_service: TaskService) -> None:
    reconciled = await task_service.reconcile_stale_worker_tasks()
    if reconciled:
        logger.warning(
            "worker.reconcile_stale_crm_tasks",
            service="crm_worker",
            reconciled=reconciled,
        )


broker = wire_worker("crm")
worker_app = build_worker(
    broker,
    service_name="crm_worker",
    queue="crm",
    settings=_crm_worker_settings,
    di_class=CrmWorkerDi,
    database="crm_url",
    lifecycle=(recipe(reconcile_crm_worker_tasks),),
)

__all__ = ["worker_app"]
