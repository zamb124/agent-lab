"""DI процесса scheduler: control-plane расписаний компании."""

from typing import Annotated

from taskiq.abc.broker import AsyncBroker

from apps.scheduler.config import SchedulerSettings
from apps.worker_manifest import wire_brokers
from core.di import http_di, recipe, task_di
from core.di.platform import PlatformDi
from core.scheduler import SchedulerService
from core.tasks.registry import registered_queue_brokers

wire_brokers()


def scheduler_broker_for_queue(queue_name: str) -> AsyncBroker:
    """Брокер TaskIQ для AsyncKicker: задача должна быть зарегистрирована на этом брокере."""
    brokers = registered_queue_brokers()
    if queue_name not in brokers:
        raise ValueError(f"Unknown queue for scheduler kicker: {queue_name}")
    return brokers[queue_name]


@recipe
def scheduler_service(settings: SchedulerSettings) -> SchedulerService:
    return SchedulerService(
        redis_url=settings.tasks.broker_url,
        broker_for_queue=scheduler_broker_for_queue,
    )


class SchedulerDi(PlatformDi, recipes=(scheduler_service,)):
    scheduler_service: SchedulerService


Di = Annotated[SchedulerDi, http_di(SchedulerDi), task_di(SchedulerDi)]
