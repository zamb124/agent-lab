"""TaskIQ task-name contract для flows worker."""

TASK_PROCESS_FLOW = "process_flow_task"
TASK_EXECUTE_SCHEDULED = "execute_scheduled_task"
TASK_EXECUTE_NODE = "execute_node"
TASK_EXECUTE_TOOL = "execute_tool"
TASK_EXECUTE_EVALUATION_RUN = "execute_evaluation_run"
TASK_ENQUEUE_PENDING_EVALUATION_RUNS = "enqueue_pending_evaluation_runs"
TASK_RUN_EVALUATION_GATE_POLICY = "run_evaluation_gate_policy"
TASK_RUN_EVALUATION_MONITOR_CYCLE = "run_evaluation_monitor_cycle"
TASK_INVOKE_LLM = "invoke_llm"
TASK_INIT_COMPANY_RESOURCES = "init_company_resources"

__all__ = [
    "TASK_PROCESS_FLOW",
    "TASK_EXECUTE_SCHEDULED",
    "TASK_EXECUTE_NODE",
    "TASK_EXECUTE_TOOL",
    "TASK_EXECUTE_EVALUATION_RUN",
    "TASK_ENQUEUE_PENDING_EVALUATION_RUNS",
    "TASK_RUN_EVALUATION_GATE_POLICY",
    "TASK_RUN_EVALUATION_MONITOR_CYCLE",
    "TASK_INVOKE_LLM",
    "TASK_INIT_COMPANY_RESOURCES",
]
