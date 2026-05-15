"""
Точка входа для TaskIQ scheduler.

Запуск: taskiq scheduler apps.scheduler.scheduler:scheduler
"""

from apps.scheduler.config import get_scheduler_settings
from core.logging import setup_logging

settings = get_scheduler_settings()
setup_logging(service_name="scheduler", logging_config=settings.logging)

# Импорты модулей с @broker.task — регистрируют задачи на брокерах до create_scheduler и проверки.
import apps.crm_worker.tasks.daily_summary_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.reembed_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.scheduled_integration_sync_tasks  # noqa: F401, E402
import apps.crm_worker.tasks.suggest_tasks  # noqa: F401, E402
import apps.flows.src.tasks.eval_task  # noqa: F401, E402
import apps.flows.src.tasks.flow_tasks  # noqa: F401, E402
import apps.flows.src.tasks.llm_tasks  # noqa: F401, E402
import apps.flows.src.tasks.scheduled_tasks  # noqa: F401, E402
import apps.flows.src.tasks.tool_tasks  # noqa: F401, E402
import apps.idle_worker.tasks.calendar_sync_tasks  # noqa: F401, E402
import apps.idle_worker.tasks.llm_models_tasks  # noqa: F401, E402
import apps.idle_worker.tasks.openrouter_free_models_tasks  # noqa: F401, E402
import apps.idle_worker.tasks.push_notification_tasks  # noqa: F401, E402
import apps.idle_worker.tasks.span_billing_settlement_tasks  # noqa: F401, E402
import apps.rag_worker.tasks.maintenance_tasks  # noqa: F401, E402
from apps.crm.scheduled_integration_constants import (  # noqa: E402
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
)
from apps.crm.scheduled_task_constants import (  # noqa: E402
    CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME,
    CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
)
from apps.scheduler.dispatch import (  # noqa: E402
    create_scheduler,
    require_tasks_registered_for_scheduler,
)

_FLOWS_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "process_flow_task",
    "execute_tool",
    "invoke_llm",
    "execute_scheduled_task",
    "apps.flows.src.tasks.eval_task:execute_inline_code",
)

_IDLE_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "push_config_set",
    "push_config_get",
    "push_config_list",
    "push_config_delete",
    "push_notification_send",
    "send_task_update",
    "send_task_completed",
    "send_task_failed",
    "send_task_input_required",
    "sync_llm_models_task",
    "refresh_openrouter_free_models_task",
    "calendar_sync_tick",
    "calendar_sync_meeting_reminder_tick",
    "span_billing_settlement_tick",
)

_RAG_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "rag_cleanup_expired_documents_tick",
    "rag_reembed_stale_documents_tick",
)

_CRM_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
    CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
    CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME,
)

require_tasks_registered_for_scheduler(
    flows_worker_task_names=_FLOWS_SCHEDULER_REQUIRED_TASK_NAMES,
    idle_queue_task_names=_IDLE_SCHEDULER_REQUIRED_TASK_NAMES,
    crm_queue_task_names=_CRM_SCHEDULER_REQUIRED_TASK_NAMES,
    rag_queue_task_names=_RAG_SCHEDULER_REQUIRED_TASK_NAMES,
)

scheduler = create_scheduler(settings.database.redis_url)

__all__ = ["scheduler"]
