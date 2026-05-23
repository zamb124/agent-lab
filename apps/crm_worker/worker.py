"""
Точка входа для CRM Worker.

Запуск: taskiq worker apps.crm_worker.worker:worker_app
"""

# ruff: noqa: E402, I001

from apps.crm.config import CRMSettings
from core.config import set_settings
from core.config.loader import load_merged_config
from core.tasks.logging_init import setup_worker_logging_early

_merged_crm = load_merged_config(service_name="crm", silent=True)
_crm_worker_settings = CRMSettings.model_validate(_merged_crm)
setup_worker_logging_early("crm_worker", logging_config=_crm_worker_settings.logging)
set_settings(_crm_worker_settings)

from taskiq import TaskiqState  # noqa: E402

from apps.crm.container import get_crm_container  # noqa: E402
from apps.crm_worker.broker import broker as worker_app, recovery_handler  # noqa: E402
from core.billing import set_billing_service  # noqa: E402
from core.files.processors import initialize_default_processors  # noqa: E402
from core.logging import get_logger  # noqa: E402
from core.tasks.broker import register_worker_events  # noqa: E402
from core.tracing import setup_tracing  # noqa: E402
from core.tracing.tracer import set_span_repository, set_tracing_service_name  # noqa: E402
from core.websocket.manager import notification_manager  # noqa: E402

logger = get_logger(__name__)


async def crm_worker_startup(state: TaskiqState) -> None:
    settings = _crm_worker_settings
    container = get_crm_container()
    state.container = container

    reconciled = await container.task_service.reconcile_stale_worker_tasks()
    if reconciled:
        logger.warning(
            "worker.reconcile_stale_crm_tasks",
            service="crm_worker",
            reconciled=reconciled,
        )

    await recovery_handler()

    initialize_default_processors(container.file_repository)
    logger.info("worker.file_processors_initialized", service="crm_worker")
    set_billing_service(container.billing_service)
    logger.info("worker.billing_initialized", service="crm_worker")
    if settings.tracing.enabled:
        setup_tracing(settings.tracing)
        if settings.tracing.postgres_enabled and hasattr(container, "span_repository"):
            if not settings.database.tracing_url:
                raise ValueError(
                    "tracing.postgres_enabled требует database.tracing_url (DATABASE__TRACING_URL)"
                )
            set_tracing_service_name("crm_worker")
            set_span_repository(container.span_repository)
        logger.info("worker.tracing_initialized", service="crm_worker")
    await notification_manager.start_redis_listener(settings.database.redis_url)
    logger.info("worker.starting", service="crm_worker")


async def crm_worker_shutdown(state: TaskiqState) -> None:
    await notification_manager.stop_redis_listener()
    logger.info("worker.stopping", service="crm_worker")


register_worker_events(
    worker_app,
    crm_worker_startup,
    crm_worker_shutdown,
    service_name="crm_worker",
)

import apps.crm_worker.tasks.analysis_tasks as _analysis_tasks  # noqa: E402
import apps.crm_worker.tasks.daily_summary_tasks as _daily_summary_tasks  # noqa: E402
import apps.crm_worker.tasks.draft_repair_tasks as _draft_repair_tasks  # noqa: E402
import apps.crm_worker.tasks.knowledge_import_tasks as _knowledge_import_tasks  # noqa: E402
import apps.crm_worker.tasks.namespace_integration_tasks as _namespace_integration_tasks  # noqa: E402
import apps.crm_worker.tasks.note_markdown_tasks as _note_markdown_tasks  # noqa: E402
import apps.crm_worker.tasks.reembed_tasks as _reembed_tasks  # noqa: E402
import apps.crm_worker.tasks.scheduled_integration_sync_tasks as _scheduled_integration_sync_tasks  # noqa: E402
import apps.crm_worker.tasks.suggest_tasks as _suggest_tasks  # noqa: E402

_TASK_REGISTRATION_MODULES = (
    _analysis_tasks,
    _daily_summary_tasks,
    _draft_repair_tasks,
    _knowledge_import_tasks,
    _namespace_integration_tasks,
    _note_markdown_tasks,
    _reembed_tasks,
    _scheduled_integration_sync_tasks,
    _suggest_tasks,
)

__all__ = ["worker_app"]
