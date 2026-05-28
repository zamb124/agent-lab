"""
Модуль core scheduler.

Предоставляет модели, репозиторий и сервис для scheduled tasks.
RedisScheduleSource — через get_schedule_source.

Примечание: create_scheduler перенесён в apps/scheduler/dispatch.py
(зависит от apps/ брокеров, не может жить в core/).
"""

from core.scheduler.models import (
    ContentType,
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    PlatformScheduleUpdateStatusRequest,
    ScheduledTaskInfo,
    ScheduledTaskStatus,
)
from core.scheduler.repository import SchedulerTaskRepository
from core.scheduler.service import SchedulerService
from core.scheduler.source import get_schedule_source, reset_schedule_source

__all__ = [
    "get_schedule_source",
    "reset_schedule_source",
    "ContentType",
    "ScheduledTaskStatus",
    "ScheduledTaskInfo",
    "PlatformScheduleType",
    "PlatformScheduleCreateRequest",
    "PlatformScheduleUpdateStatusRequest",
    "PlatformScheduleFilter",
    "PlatformScheduledTask",
    "PlatformRedisScheduleSnapshot",
    "SchedulerTaskRepository",
    "SchedulerService",
]

