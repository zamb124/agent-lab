"""
Точка входа для TaskIQ scheduler.

Запуск: taskiq scheduler apps.scheduler.scheduler:scheduler
"""

from apps.scheduler.config import get_scheduler_settings
from core.logging.setup import setup_logging

settings = get_scheduler_settings()
setup_logging(service_name="scheduler", logging_config=settings.logging)

# Импорты модулей с @broker.task — регистрируют задачи на брокерах до create_scheduler и проверки.
import apps.crm_worker.tasks.daily_summary_tasks as _crm_daily_summary_tasks  # noqa: E402
import apps.crm_worker.tasks.reembed_tasks as _crm_reembed_tasks  # noqa: E402
import apps.crm_worker.tasks.scheduled_integration_sync_tasks as _crm_scheduled_integration_sync_tasks  # noqa: E402
import apps.crm_worker.tasks.suggest_tasks as _crm_suggest_tasks  # noqa: E402
import apps.flows.src.tasks.flow_tasks as _flows_flow_tasks  # noqa: E402
import apps.flows.src.tasks.llm_tasks as _flows_llm_tasks  # noqa: E402
import apps.flows.src.tasks.scheduled_tasks as _flows_scheduled_tasks  # noqa: E402
import apps.flows.src.tasks.tool_tasks as _flows_tool_tasks  # noqa: E402
import apps.idle_worker.tasks.calendar_sync_tasks as _idle_calendar_sync_tasks  # noqa: E402
import apps.idle_worker.tasks.file_retention_tasks as _idle_file_retention_tasks  # noqa: E402
import apps.idle_worker.tasks.llm_models_tasks as _idle_llm_models_tasks  # noqa: E402
import apps.idle_worker.tasks.mcp_catalog_tasks as _mcp_catalog_tasks  # noqa: E402
import apps.idle_worker.tasks.payment_sync_tasks as _idle_payment_sync_tasks  # noqa: E402
import apps.idle_worker.tasks.platform_free_models_tasks as _idle_platform_free_models_tasks  # noqa: E402
import apps.idle_worker.tasks.push_notification_tasks as _idle_push_notification_tasks  # noqa: E402
import apps.idle_worker.tasks.span_billing_settlement_tasks as _idle_span_billing_settlement_tasks  # noqa: E402
import apps.rag_worker.tasks.maintenance_tasks as _rag_maintenance_tasks  # noqa: E402
import apps.search_worker.tasks.crawl_tasks as _search_crawl_tasks  # noqa: E402
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

_TASK_REGISTRATION_MODULES = (
    _crm_daily_summary_tasks,
    _crm_reembed_tasks,
    _crm_scheduled_integration_sync_tasks,
    _crm_suggest_tasks,
    _flows_flow_tasks,
    _flows_llm_tasks,
    _flows_scheduled_tasks,
    _flows_tool_tasks,
    _idle_file_retention_tasks,
    _mcp_catalog_tasks,
    _idle_calendar_sync_tasks,
    _idle_llm_models_tasks,
    _idle_platform_free_models_tasks,
    _idle_payment_sync_tasks,
    _idle_push_notification_tasks,
    _idle_span_billing_settlement_tasks,
    _rag_maintenance_tasks,
    _search_crawl_tasks,
)

_FLOWS_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "process_flow_task",
    "execute_tool",
    "invoke_llm",
    "execute_scheduled_task",
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
    "refresh_platform_free_models_task",
    "payment_sync_tick",
    "calendar_sync_tick",
    "calendar_sync_meeting_reminder_tick",
    "span_billing_settlement_tick",
    "file_retention_purge_tick",
    "file_retention_backfill_tick",
    "mcp_catalog_crawl_task",
    "mcp_catalog_provision_companies_task",
    "mcp_catalog_resync_tools_task",
)

_RAG_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "rag_cleanup_expired_documents_tick",
    "rag_reembed_stale_documents_tick",
    "rag_cleanup_orphan_company_chunks_tick",
)

_CRM_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC_TASK_NAME,
    CRM_REEMBED_STALE_DOCUMENTS_TASK_NAME,
    CRM_GENERATE_NAMESPACE_SUGGESTS_TASK_NAME,
    CRM_RECONCILE_DAILY_SUMMARY_TASK_NAME,
)

_SEARCH_SCHEDULER_REQUIRED_TASK_NAMES: tuple[str, ...] = (
    "crawl_orchestrator_tick",
    "crawl_discover_domain",
    "crawl_fetch_url",
    "crawl_import_seed_domains",
    "crawl_reclaim_stale_fetching",
)

require_tasks_registered_for_scheduler(
    flows_worker_task_names=_FLOWS_SCHEDULER_REQUIRED_TASK_NAMES,
    idle_queue_task_names=_IDLE_SCHEDULER_REQUIRED_TASK_NAMES,
    crm_queue_task_names=_CRM_SCHEDULER_REQUIRED_TASK_NAMES,
    rag_queue_task_names=_RAG_SCHEDULER_REQUIRED_TASK_NAMES,
    search_queue_task_names=_SEARCH_SCHEDULER_REQUIRED_TASK_NAMES,
)

scheduler = create_scheduler(settings.database.redis_url)

__all__ = ["scheduler"]
