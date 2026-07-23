"""DI контейнер scheduler сервиса."""

from __future__ import annotations

from taskiq.abc.broker import AsyncBroker

from apps.platform_tasks.wiring import wire_brokers
from apps.scheduler.config import get_scheduler_settings
from core.container import BaseContainer, ContainerRegistry, lazy
from core.logging import get_logger
from core.scheduler import SchedulerService, SchedulerTaskRepository
from core.tasks.registry import registered_queue_brokers

logger = get_logger(__name__)

wire_brokers()


def scheduler_broker_for_queue(queue_name: str) -> AsyncBroker:
    """Брокер TaskIQ для AsyncKicker: задача должна быть зарегистрирована на этом брокере."""
    brokers = registered_queue_brokers()
    if queue_name not in brokers:
        raise ValueError(f"Неизвестная очередь для scheduler kicker: {queue_name}")
    return brokers[queue_name]


class SchedulerContainer(BaseContainer):
    """Контейнер зависимостей scheduler."""

    @lazy
    def scheduler_task_repository(self) -> SchedulerTaskRepository:
        settings = get_scheduler_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required for scheduler repository")
        return SchedulerTaskRepository(db_url=settings.database.shared_url)

    @lazy
    def scheduler_service(self) -> SchedulerService:
        settings = get_scheduler_settings()
        return SchedulerService(
            repository=self.scheduler_task_repository,
            redis_url=settings.tasks.broker_url,
            broker_for_queue=scheduler_broker_for_queue,
        )


def _create_scheduler_container() -> SchedulerContainer:
    settings = get_scheduler_settings()
    if not settings.database.shared_url:
        raise ValueError("database.shared_url is required")
    return SchedulerContainer(
        db_url=settings.database.shared_url,
        shared_db_url=settings.database.shared_url,
    )


_scheduler_registry: ContainerRegistry[SchedulerContainer] = ContainerRegistry(
    _create_scheduler_container, name="SchedulerContainer"
)

get_scheduler_container = _scheduler_registry.get
set_scheduler_container = _scheduler_registry.set
reset_scheduler_container = _scheduler_registry.reset
