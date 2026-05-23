"""DI контейнер scheduler сервиса."""

from __future__ import annotations

from typing import Any

from apps.crm_worker.broker import broker as crm_broker
from apps.flows_worker.broker import broker as flows_broker
from apps.idle_worker.broker import broker as idle_broker
from apps.rag_worker.broker import broker as rag_broker
from apps.scheduler.config import get_scheduler_settings
from apps.sync.realtime.broker import broker as sync_broker
from core.container import BaseContainer, lazy
from core.logging import get_logger
from core.scheduler import SchedulerService, SchedulerTaskRepository

logger = get_logger(__name__)


def scheduler_broker_for_queue(queue_name: str) -> Any:
    """Брокер TaskIQ для AsyncKicker: задача должна быть зарегистрирована на этом брокере."""
    mapping: dict[str, Any] = {
        "flows_worker": flows_broker,
        "idle": idle_broker,
        "crm": crm_broker,
        "rag": rag_broker,
        "sync": sync_broker,
    }
    if queue_name not in mapping:
        raise ValueError(f"Неизвестная очередь для scheduler kicker: {queue_name}")
    return mapping[queue_name]


class SchedulerContainer(BaseContainer):
    """Контейнер зависимостей scheduler."""

    @lazy
    def scheduler_task_repository(self):
        settings = get_scheduler_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required for scheduler repository")
        return SchedulerTaskRepository(db_url=settings.database.shared_url)

    @lazy
    def scheduler_service(self):
        settings = get_scheduler_settings()
        return SchedulerService(
            repository=self.scheduler_task_repository,
            redis_url=settings.database.redis_url,
            broker_for_queue=scheduler_broker_for_queue,
        )


_scheduler_container: SchedulerContainer | None = None


def get_scheduler_container() -> SchedulerContainer:
    global _scheduler_container
    if _scheduler_container is None:
        settings = get_scheduler_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required")

        _scheduler_container = SchedulerContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("SchedulerContainer инициализирован")
    return _scheduler_container


def set_scheduler_container(container: SchedulerContainer) -> None:
    global _scheduler_container
    _scheduler_container = container


def reset_scheduler_container() -> None:
    global _scheduler_container
    _scheduler_container = None
