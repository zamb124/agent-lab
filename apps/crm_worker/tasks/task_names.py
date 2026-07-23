"""Declaration-модуль CRM задач (очередь ``crm``).

Лёгкий: только объявления TaskSpec. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``).

Единственный источник имён задач CRM — этот модуль. Для schedule API
используйте ``SPEC.name`` напрямую (без ``*_TASK_NAME``-обёрток).
"""

from core.tasks import declare_task

CRM_PROCESS_NOTE = declare_task("crm_process_note", queue="crm")
CRM_RUN_KNOWLEDGE_IMPORT = declare_task("crm_run_knowledge_import", queue="crm")
CRM_RUN_NAMESPACE_INTEGRATION_JOB = declare_task(
    "crm_run_namespace_integration_job", queue="crm"
)
CRM_REPAIR_NOTE_ANALYSIS_DRAFT = declare_task(
    "crm_repair_note_analysis_draft", queue="crm"
)
CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN = declare_task(
    "crm_format_note_description_markdown", queue="crm"
)
CRM_REBUILD_DAILY_SUMMARY = declare_task("crm_rebuild_daily_summary", queue="crm")
CRM_REBUILD_PERIOD_SUMMARY = declare_task("crm_rebuild_period_summary", queue="crm")

CRM_RECONCILE_DAILY_SUMMARY = declare_task(
    "crm_reconcile_daily_summary", queue="crm", scheduled=True
)
CRM_GENERATE_NAMESPACE_SUGGESTS = declare_task(
    "crm_generate_namespace_suggests_tick",
    queue="crm",
    scheduled=True,
    retry=True,
    max_retries=3,
)
CRM_REEMBED_STALE_DOCUMENTS = declare_task(
    "crm_reembed_stale_documents_tick",
    queue="crm",
    scheduled=True,
    retry=True,
    max_retries=2,
)
SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC = declare_task(
    "scheduled_namespace_integration_unified_sync",
    queue="crm",
    scheduled=True,
    retry=True,
    max_retries=2,
)

__all__ = [
    "CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN",
    "CRM_GENERATE_NAMESPACE_SUGGESTS",
    "CRM_PROCESS_NOTE",
    "CRM_REBUILD_DAILY_SUMMARY",
    "CRM_REBUILD_PERIOD_SUMMARY",
    "CRM_RECONCILE_DAILY_SUMMARY",
    "CRM_REEMBED_STALE_DOCUMENTS",
    "CRM_REPAIR_NOTE_ANALYSIS_DRAFT",
    "CRM_RUN_KNOWLEDGE_IMPORT",
    "CRM_RUN_NAMESPACE_INTEGRATION_JOB",
    "SCHEDULED_NAMESPACE_INTEGRATION_UNIFIED_SYNC",
]
