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
_segment = resolve_files_route_segment("crm_summary_worker")
set_files_route_segment(_segment)

import importlib

from taskiq import TaskiqState

from apps.crm.container import get_crm_container
from apps.platform_tasks.wiring import wire_worker
from core.billing import set_billing_service
from core.files.processors import initialize_default_processors
from core.tasks.worker_bootstrap import build_worker, init_worker_tracing

# side-effect: register CRM platform event catalog types for this process
_ = importlib.import_module("apps.crm.services.crm_entity_events")
_ = importlib.import_module("apps.crm.services.crm_realtime_events")

broker = wire_worker("crm_summary")


async def _startup(state: TaskiqState) -> None:
    container = get_crm_container()
    container.bind_files_route_segment(_segment)
    state.container = container

    initialize_default_processors(container.file_repository)
    set_billing_service(container.billing_service)
    init_worker_tracing("crm_summary_worker", container)


async def _shutdown(state: TaskiqState) -> None:
    _ = state


worker_app = build_worker(
    broker,
    service_name="crm_summary_worker",
    queue="crm_summary",
    on_startup=_startup,
    on_shutdown=_shutdown,
)

__all__ = ["worker_app"]
