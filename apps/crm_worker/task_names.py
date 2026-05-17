"""TaskIQ task-name contract for CRM worker tasks."""

CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME = (
    "apps.crm_worker.tasks.knowledge_import_tasks:run_knowledge_import_task"
)
CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME = (
    "apps.crm_worker.tasks.namespace_integration_tasks:run_namespace_integration_job"
)
CRM_PROCESS_NOTE_TASK_NAME = "apps.crm_worker.tasks.analysis_tasks:process_note_task"
CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME = (
    "apps.crm_worker.tasks.draft_repair_tasks:repair_note_analysis_draft_task"
)
CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME = (
    "apps.crm_worker.tasks.note_markdown_tasks:format_note_description_markdown_task"
)
CRM_REBUILD_DAILY_SUMMARY_TASK_NAME = "crm_rebuild_daily_summary"
CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME = "crm_rebuild_period_summary"

__all__ = [
    "CRM_FORMAT_NOTE_DESCRIPTION_MARKDOWN_TASK_NAME",
    "CRM_PROCESS_NOTE_TASK_NAME",
    "CRM_REBUILD_DAILY_SUMMARY_TASK_NAME",
    "CRM_REBUILD_PERIOD_SUMMARY_TASK_NAME",
    "CRM_REPAIR_NOTE_ANALYSIS_DRAFT_TASK_NAME",
    "CRM_RUN_KNOWLEDGE_IMPORT_TASK_NAME",
    "CRM_RUN_NAMESPACE_INTEGRATION_JOB_TASK_NAME",
]
