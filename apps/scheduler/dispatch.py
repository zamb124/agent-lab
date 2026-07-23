"""
QueueAwareTaskiqScheduler и dispatch брокеров.

Перенесено из core/scheduler — содержит импорты apps/ брокеров через
``core.tasks.registry``, поэтому живёт в apps/, а не в core/.
"""

import uuid
from typing import override

from taskiq import TaskiqScheduler
from taskiq.abc.schedule_source import ScheduleSource
from taskiq.exceptions import ScheduledTaskCancelledError
from taskiq.kicker import AsyncKicker
from taskiq.scheduler.scheduled_task import ScheduledTask
from taskiq.utils import maybe_awaitable
from taskiq_redis import RedisStreamBroker

from core.logging import get_logger
from core.logging.attributes import EVENT_TASK_SCHEDULED
from core.scheduler.source import get_schedule_source
from core.tasks.registry import (
    get_task_spec,
    registered_queue_brokers,
    scheduled_task_specs,
)

logger = get_logger(__name__)


def require_scheduled_tasks_registered() -> None:
    """Падение scheduler-процесса, если scheduled-задачи не на брокерах."""
    missing: list[str] = []
    brokers = registered_queue_brokers()
    for spec in scheduled_task_specs():
        broker = brokers.get(spec.queue)
        if broker is None or broker.find_task(spec.name) is None:
            missing.append(f"{spec.queue}:{spec.name}")
    if missing:
        raise RuntimeError(
            "TaskIQ scheduler: не зарегистрированы scheduled-задачи: "
            + ", ".join(sorted(missing))
        )
    logger.info(
        "task.scheduler_registration_ok",
        scheduled_count=len(scheduled_task_specs()),
        queues=sorted(brokers.keys()),
    )


class QueueAwareTaskiqScheduler(TaskiqScheduler):
    @override
    async def on_ready(self, source: ScheduleSource, task: ScheduledTask) -> None:
        """
        Kick через брокер целевой очереди (labels['queue_name'] или TaskSpec.queue).
        """
        raw_qn = task.labels.get("queue_name")
        if raw_qn is None or (isinstance(raw_qn, str) and not raw_qn.strip()):
            task.labels["queue_name"] = get_task_spec(task.task_name).queue
        queue_name = str(task.labels["queue_name"]).strip()
        task.labels["queue_name"] = queue_name
        brokers = registered_queue_brokers()
        target_broker = brokers.get(queue_name)
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
            kicker: AsyncKicker[..., str] = AsyncKicker(
                task.task_name,
                target_broker,
                task.labels,
            )
            _ = await (
                kicker.with_labels(
                    schedule_id=task.schedule_id,
                    trace_id=trace_id,
                    request_id=request_id,
                    service_name=service_name,
                    triggered_by="scheduler",
                )
                .with_task_id(task_id=task.task_id)
                .kiq(*task.args, **task.kwargs)
            )
            await maybe_awaitable(source.post_send(task))


def create_scheduler(redis_url: str) -> TaskiqScheduler:
    """Создаёт TaskiqScheduler с RedisScheduleSource."""
    source = get_schedule_source(redis_url)
    brokers = registered_queue_brokers()
    flows_broker = brokers.get("flows_worker")
    if not isinstance(flows_broker, RedisStreamBroker):
        raise RuntimeError(
            "create_scheduler: брокер flows_worker не зарегистрирован (вызовите wire_all)"
        )
    scheduler = QueueAwareTaskiqScheduler(broker=flows_broker, sources=[source])
    logger.info("task.scheduler_created")
    return scheduler


__all__ = ["create_scheduler", "require_scheduled_tasks_registered"]
