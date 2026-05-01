"""
QueueAwareTaskiqScheduler и dispatch брокеров.

Перенесено из core/scheduler/scheduler.py — содержит импорты apps/ брокеров,
поэтому должно жить в apps/, а не в core/.
"""

import uuid
from typing import Any

from taskiq import TaskiqScheduler
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.exceptions import ScheduledTaskCancelledError
from taskiq.kicker import AsyncKicker
from taskiq.scheduler.scheduled_task import ScheduledTask
from taskiq.utils import maybe_awaitable

from core.logging import get_logger
from core.logging.attributes import EVENT_TASK_SCHEDULED
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

_QUEUE_NAME_TO_BROKER: dict[str, Any] = {
    "flows_worker": flows_broker,
    "idle": idle_broker,
    "crm": crm_broker,
    "rag": rag_broker,
    "sync": sync_broker,
}


def require_tasks_registered_for_scheduler(
    *,
    flows_worker_task_names: tuple[str, ...],
    idle_queue_task_names: tuple[str, ...],
    crm_queue_task_names: tuple[str, ...] = (),
    rag_queue_task_names: tuple[str, ...] = (),
) -> None:
    """
    Падение процесса taskiq scheduler при старте, если обязательные задачи
    не зарегистрированы на брокерах (забыты импорты в apps/scheduler/scheduler.py).
    """
    missing_flows = [n for n in flows_worker_task_names if flows_broker.find_task(n) is None]
    missing_idle = [n for n in idle_queue_task_names if idle_broker.find_task(n) is None]
    missing_crm = [n for n in crm_queue_task_names if crm_broker.find_task(n) is None]
    missing_rag = [n for n in rag_queue_task_names if rag_broker.find_task(n) is None]
    if missing_flows or missing_idle or missing_crm or missing_rag:
        parts: list[str] = []
        if missing_flows:
            parts.append(f"flows_worker broker: {missing_flows}")
        if missing_idle:
            parts.append(f"idle broker: {missing_idle}")
        if missing_crm:
            parts.append(f"crm broker: {missing_crm}")
        if missing_rag:
            parts.append(f"rag broker: {missing_rag}")
        raise RuntimeError(
            "TaskIQ scheduler: не зарегистрированы задачи. Добавьте импорт модулей с @broker.task "
            f"в apps/scheduler/scheduler.py. Отсутствуют: {'; '.join(parts)}"
        )
    logger.info(
        "task.scheduler_registration_ok",
        flows_worker_count=len(flows_worker_task_names),
        idle_count=len(idle_queue_task_names),
        crm_count=len(crm_queue_task_names),
        rag_count=len(rag_queue_task_names),
    )


class QueueAwareTaskiqScheduler(TaskiqScheduler):
    async def on_ready(self, source: ScheduleSource, task: ScheduledTask) -> None:
        """
        TaskIQ по умолчанию шлёт kick через self.broker (flows). У RedisStreamBroker
        очередь = labels['queue_name'] or broker.queue_name; пустая строка даёт fallback
        на flows_worker, из-за чего idle-задачи оказываются в flows и воркер их не находит.
        Здесь нормализуем queue_name и кикаем через брокер целевой очереди.
        """
        raw_qn = task.labels.get("queue_name")
        if raw_qn is None or (isinstance(raw_qn, str) and not raw_qn.strip()):
            task.labels["queue_name"] = _resolve_queue_name(task.task_name)
        queue_name = str(task.labels["queue_name"]).strip()
        task.labels["queue_name"] = queue_name
        target_broker = _QUEUE_NAME_TO_BROKER.get(queue_name)
        if target_broker is None:
            raise ValueError(f"Неизвестная очередь для dispatch планировщика: {queue_name}")
        try:
            await maybe_awaitable(source.pre_send(task))
        except ScheduledTaskCancelledError:
            logger.info(
                "task.scheduled_cancelled",
                task_name=task.task_name,
                schedule_id=task.schedule_id,
            )
        else:
            trace_id = task.labels.get("trace_id") or f"sched:{uuid.uuid4().hex}"
            request_id = task.labels.get("request_id") or f"sched:{uuid.uuid4().hex}"
            service_name = task.labels.get("service_name") or "scheduler"
            task.labels["trace_id"] = trace_id
            task.labels["request_id"] = request_id
            task.labels["service_name"] = service_name
            task.labels["triggered_by"] = "scheduler"
            logger.info(
                EVENT_TASK_SCHEDULED,
                task_name=task.task_name,
                queue=queue_name,
                schedule_id=task.schedule_id,
                trace_id=trace_id,
                request_id=request_id,
            )
            await (
                AsyncKicker(task.task_name, target_broker, task.labels)
                .with_labels(
                    schedule_id=task.schedule_id,
                    trace_id=trace_id,
                    request_id=request_id,
                    service_name=service_name,
                    triggered_by="scheduler",
                )
                .with_task_id(task_id=task.task_id)
                .kiq(
                    *task.args,
                    **task.kwargs,
                )
            )
            await maybe_awaitable(source.post_send(task))


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
    
    logger.info("task.scheduler_created")
    return scheduler


__all__ = ["create_scheduler", "require_tasks_registered_for_scheduler"]
