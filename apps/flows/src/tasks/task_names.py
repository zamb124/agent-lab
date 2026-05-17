"""TaskIQ task-name contract для flows worker."""

TASK_PROCESS_FLOW = "process_flow_task"
TASK_EXECUTE_SCHEDULED = "execute_scheduled_task"
TASK_EXECUTE_NODE = "execute_node"
TASK_EXECUTE_TOOL = "execute_tool"
TASK_INVOKE_LLM = "invoke_llm"
TASK_INIT_COMPANY_RESOURCES = "init_company_resources"

__all__ = [
    "TASK_PROCESS_FLOW",
    "TASK_EXECUTE_SCHEDULED",
    "TASK_EXECUTE_NODE",
    "TASK_EXECUTE_TOOL",
    "TASK_INVOKE_LLM",
    "TASK_INIT_COMPANY_RESOURCES",
]
