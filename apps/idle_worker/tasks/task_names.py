"""Declaration-модуль idle задач (очередь ``idle``).

Лёгкий: только объявления. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``). Почтовые задачи объявлены отдельно в
``core/mail/task_names.py`` и здесь не дублируются.
"""

from core.tasks import declare_task

TASK_PUSH_CONFIG_SET = declare_task("push_config_set", queue="idle")
TASK_PUSH_CONFIG_GET = declare_task("push_config_get", queue="idle")
TASK_PUSH_CONFIG_LIST = declare_task("push_config_list", queue="idle")
TASK_PUSH_CONFIG_DELETE = declare_task("push_config_delete", queue="idle")
TASK_PUSH_NOTIFICATION_SEND = declare_task(
    "push_notification_send", queue="idle", retry=True, max_retries=5
)
TASK_SEND_TASK_UPDATE = declare_task(
    "send_task_update", queue="idle", retry=True, max_retries=3
)
TASK_SEND_TASK_COMPLETED = declare_task("send_task_completed", queue="idle")
TASK_SEND_TASK_FAILED = declare_task("send_task_failed", queue="idle")
TASK_SEND_TASK_INPUT_REQUIRED = declare_task(
    "send_task_input_required", queue="idle"
)

TASK_INIT_NEW_COMPANY = declare_task(
    "company_init_new_company", queue="idle", retry=True, max_retries=3
)
TASK_INIT_SYSTEM_COMPANY = declare_task(
    "company_init_system", queue="idle", retry=True, max_retries=3
)

TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK = declare_task(
    "tool_tag_groups_describe_tick", queue="idle", scheduled=True
)

TASK_SYNC_LLM_MODELS = declare_task("sync_llm_models_task", queue="idle", scheduled=True)

TASK_REFRESH_PLATFORM_FREE_MODELS = declare_task(
    "refresh_platform_free_models_task", queue="idle", scheduled=True
)

TASK_PAYMENT_SYNC_TICK = declare_task("payment_sync_tick", queue="idle", scheduled=True)

TASK_CALENDAR_SYNC_TICK = declare_task("calendar_sync_tick", queue="idle", scheduled=True)
TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK = declare_task(
    "calendar_sync_meeting_reminder_tick", queue="idle", scheduled=True
)

TASK_SPAN_BILLING_SETTLEMENT_TICK = declare_task(
    "span_billing_settlement_tick", queue="idle", scheduled=True
)

TASK_FILE_RETENTION_PURGE_TICK = declare_task(
    "file_retention_purge_tick", queue="idle", scheduled=True
)
TASK_FILE_RETENTION_BACKFILL_TICK = declare_task(
    "file_retention_backfill_tick", queue="idle", scheduled=True
)

TASK_MCP_CATALOG_CRAWL = declare_task("mcp_catalog_crawl_task", queue="idle", scheduled=True)
TASK_MCP_CATALOG_PROVISION_COMPANIES = declare_task(
    "mcp_catalog_provision_companies_task", queue="idle"
)
TASK_MCP_CATALOG_RESYNC_TOOLS = declare_task(
    "mcp_catalog_resync_tools_task", queue="idle", scheduled=True
)

TASK_PLATFORM_SCHEDULES_GC_TICK = declare_task(
    "platform_schedules_gc_tick", queue="idle", scheduled=True
)

TASK_REDIS_INVENTORY_TICK = declare_task("redis_inventory_tick", queue="idle", scheduled=True)

TASK_NAMESPACE_PERSONAL_BACKFILL = declare_task("namespace_personal_backfill", queue="idle")

__all__ = [
    "TASK_CALENDAR_SYNC_MEETING_REMINDER_TICK",
    "TASK_CALENDAR_SYNC_TICK",
    "TASK_FILE_RETENTION_BACKFILL_TICK",
    "TASK_FILE_RETENTION_PURGE_TICK",
    "TASK_INIT_NEW_COMPANY",
    "TASK_INIT_SYSTEM_COMPANY",
    "TASK_MCP_CATALOG_CRAWL",
    "TASK_MCP_CATALOG_PROVISION_COMPANIES",
    "TASK_MCP_CATALOG_RESYNC_TOOLS",
    "TASK_NAMESPACE_PERSONAL_BACKFILL",
    "TASK_PAYMENT_SYNC_TICK",
    "TASK_PLATFORM_SCHEDULES_GC_TICK",
    "TASK_PUSH_CONFIG_DELETE",
    "TASK_PUSH_CONFIG_GET",
    "TASK_PUSH_CONFIG_LIST",
    "TASK_PUSH_CONFIG_SET",
    "TASK_PUSH_NOTIFICATION_SEND",
    "TASK_REDIS_INVENTORY_TICK",
    "TASK_REFRESH_PLATFORM_FREE_MODELS",
    "TASK_SEND_TASK_COMPLETED",
    "TASK_SEND_TASK_FAILED",
    "TASK_SEND_TASK_INPUT_REQUIRED",
    "TASK_SEND_TASK_UPDATE",
    "TASK_SPAN_BILLING_SETTLEMENT_TICK",
    "TASK_SYNC_LLM_MODELS",
    "TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK",
]
