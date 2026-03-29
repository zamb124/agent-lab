"""DI контейнер scheduler сервиса."""

from __future__ import annotations

from typing import Optional

from core.container import BaseContainer, lazy
from core.logging import get_logger

logger = get_logger(__name__)


class SchedulerContainer(BaseContainer):
    """Контейнер зависимостей scheduler."""

    @lazy
    def scheduler_task_repository(self):
        from core.scheduler import SchedulerTaskRepository
        from apps.scheduler.config import get_scheduler_settings

        settings = get_scheduler_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required for scheduler repository")
        return SchedulerTaskRepository(db_url=settings.database.shared_url)

    @lazy
    def scheduler_service(self):
        from apps.broker.broker import broker
        from apps.scheduler.config import get_scheduler_settings
        from core.scheduler import SchedulerService

        settings = get_scheduler_settings()
        return SchedulerService(
            repository=self.scheduler_task_repository,
            broker=broker,
            redis_url=settings.database.redis_url,
        )


_scheduler_container: Optional[SchedulerContainer] = None


def get_scheduler_container() -> SchedulerContainer:
    global _scheduler_container
    if _scheduler_container is None:
        from apps.scheduler.config import get_scheduler_settings

        settings = get_scheduler_settings()
        if not settings.database.shared_url:
            raise ValueError("database.shared_url is required")

        _scheduler_container = SchedulerContainer(
            db_url=settings.database.shared_url,
            shared_db_url=settings.database.shared_url,
        )
        logger.info("SchedulerContainer инициализирован")
    return _scheduler_container


def reset_scheduler_container() -> None:
    global _scheduler_container
    _scheduler_container = None
