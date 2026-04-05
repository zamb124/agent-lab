"""
TaskiqScheduler factory.
"""

from taskiq import TaskiqScheduler
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.scheduler.scheduled_task import ScheduledTask

from core.logging import get_logger
from core.scheduler.source import get_schedule_source
from apps.crm_worker.broker import broker as crm_broker
from apps.flows_worker.broker import broker as flows_broker
from apps.idle_worker.broker import broker as idle_broker
from apps.rag_worker.broker import broker as rag_broker
from apps.sync.realtime.broker import broker as sync_broker

logger = get_logger(__name__)

_SCHEDULER_DISPATCH_BROKERS = (
    flows_broker,
    idle_broker,
    crm_broker,
    rag_broker,
    sync_broker,
)


def require_tasks_registered_for_scheduler(
    *,
    flows_worker_task_names: tuple[str, ...],
    idle_queue_task_names: tuple[str, ...],
) -> None:
    """
    Падение процесса taskiq scheduler при старте, если обязательные задачи
    не зарегистрированы на брокерах (забыты импорты в apps/scheduler/scheduler.py).
    """
    missing_flows = [n for n in flows_worker_task_names if flows_broker.find_task(n) is None]
    missing_idle = [n for n in idle_queue_task_names if idle_broker.find_task(n) is None]
    if missing_flows or missing_idle:
        parts: list[str] = []
        if missing_flows:
            parts.append(f"flows_worker broker: {missing_flows}")
        if missing_idle:
            parts.append(f"idle broker: {missing_idle}")
        raise RuntimeError(
            "TaskIQ scheduler: не зарегистрированы задачи. Добавьте импорт модулей с @broker.task "
            f"в apps/scheduler/scheduler.py. Отсутствуют: {'; '.join(parts)}"
        )
    logger.info(
        "TaskIQ scheduler: проверка регистрации задач OK (flows_worker=%s, idle=%s)",
        len(flows_worker_task_names),
        len(idle_queue_task_names),
    )


class QueueAwareTaskiqScheduler(TaskiqScheduler):
    async def on_ready(self, source: ScheduleSource, task: ScheduledTask) -> None:
        if "queue_name" not in task.labels:
            task.labels["queue_name"] = _resolve_queue_name(task.task_name)
        await super().on_ready(source, task)


def _resolve_queue_name(task_name: str) -> str:
    for broker in _SCHEDULER_DISPATCH_BROKERS:
        found_task = broker.find_task(task_name)
        if found_task is None:
            continue
        queue_name = found_task.labels.get("queue_name")
        if not queue_name:
            raise ValueError(f"queue_name label is required for task: {task_name}")
        return str(queue_name)
    raise ValueError(f"task is not registered in known brokers: {task_name}")


def create_scheduler(redis_url: str) -> TaskiqScheduler:
    """
    Создает TaskiqScheduler с RedisScheduleSource.
    
    Args:
        redis_url: URL Redis для schedule source
        
    Returns:
        TaskiqScheduler
    """
    source = get_schedule_source(redis_url)
    
    scheduler = QueueAwareTaskiqScheduler(
        broker=flows_broker,
        sources=[source],
    )
    
    logger.info("TaskiqScheduler создан")
    return scheduler


__all__ = ["create_scheduler", "require_tasks_registered_for_scheduler"]


