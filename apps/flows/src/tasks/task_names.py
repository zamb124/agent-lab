"""Declaration-модуль flows задач (очередь ``flows_worker``).

Лёгкий: только объявления. Импортируется и producer'ами (для ``enqueue``),
и impl-модулями (для ``@platform_task``).
"""

from core.tasks import declare_task

TASK_PROCESS_FLOW = declare_task("process_flow_task", queue="flows_worker")
TASK_EXECUTE_SCHEDULED = declare_task(
    "execute_scheduled_task", queue="flows_worker", scheduled=True
)
TASK_EXECUTE_NODE = declare_task("execute_node", queue="flows_worker")
TASK_EXECUTE_TOOL = declare_task("execute_tool", queue="flows_worker")
TASK_EXECUTE_EVALUATION_RUN = declare_task("execute_evaluation_run", queue="flows_worker")
TASK_ENQUEUE_PENDING_EVALUATION_RUNS = declare_task(
    "enqueue_pending_evaluation_runs", queue="flows_worker"
)
TASK_RUN_EVALUATION_GATE_POLICY = declare_task(
    "run_evaluation_gate_policy", queue="flows_worker"
)
TASK_RUN_EVALUATION_MONITOR_CYCLE = declare_task(
    "run_evaluation_monitor_cycle", queue="flows_worker"
)
TASK_INVOKE_LLM = declare_task("invoke_llm", queue="flows_worker")
TASK_INIT_COMPANY_RESOURCES = declare_task(
    "init_company_resources", queue="flows_worker", retry=True, max_retries=3
)
TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK = declare_task(
    "tool_tag_groups_describe_tick", queue="flows_worker", scheduled=True
)
TASK_MCP_CATALOG_CRAWL = declare_task("mcp_catalog_crawl_task", queue="flows_worker", scheduled=True)
TASK_MCP_CATALOG_PROVISION_COMPANIES = declare_task(
    "mcp_catalog_provision_companies_task", queue="flows_worker"
)
TASK_MCP_CATALOG_RESYNC_TOOLS = declare_task(
    "mcp_catalog_resync_tools_task", queue="flows_worker", scheduled=True
)
TASK_DISPATCH_EMAIL_TRIGGERS = declare_task("dispatch_email_triggers", queue="flows_worker")
TASK_FLOWS_REMOTE_TASK_FINISHED = declare_task(
    "flows_remote_task_finished", queue="flows_worker"
)

__all__ = [
    "TASK_DISPATCH_EMAIL_TRIGGERS",
    "TASK_ENQUEUE_PENDING_EVALUATION_RUNS",
    "TASK_EXECUTE_EVALUATION_RUN",
    "TASK_EXECUTE_NODE",
    "TASK_EXECUTE_SCHEDULED",
    "TASK_EXECUTE_TOOL",
    "TASK_FLOWS_REMOTE_TASK_FINISHED",
    "TASK_INIT_COMPANY_RESOURCES",
    "TASK_INVOKE_LLM",
    "TASK_MCP_CATALOG_CRAWL",
    "TASK_MCP_CATALOG_PROVISION_COMPANIES",
    "TASK_MCP_CATALOG_RESYNC_TOOLS",
    "TASK_PROCESS_FLOW",
    "TASK_RUN_EVALUATION_GATE_POLICY",
    "TASK_RUN_EVALUATION_MONITOR_CYCLE",
    "TASK_TOOL_TAG_GROUPS_DESCRIBE_TICK",
]
