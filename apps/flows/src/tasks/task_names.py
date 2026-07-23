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

__all__ = [
    "TASK_ENQUEUE_PENDING_EVALUATION_RUNS",
    "TASK_EXECUTE_EVALUATION_RUN",
    "TASK_EXECUTE_NODE",
    "TASK_EXECUTE_SCHEDULED",
    "TASK_EXECUTE_TOOL",
    "TASK_INIT_COMPANY_RESOURCES",
    "TASK_INVOKE_LLM",
    "TASK_PROCESS_FLOW",
    "TASK_RUN_EVALUATION_GATE_POLICY",
    "TASK_RUN_EVALUATION_MONITOR_CYCLE",
]
