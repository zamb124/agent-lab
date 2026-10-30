"""
Модуль core scheduler.

Предоставляет модели и сервис для scheduled tasks.
RedisScheduleSource — через get_schedule_source.

Примечание: create_scheduler перенесён в apps/scheduler/dispatch.py
(зависит от apps/ брокеров, не может жить в core/).
"""

from core.scheduler.models import (
    PlatformRedisScheduleSnapshot,
    PlatformScheduleCreateRequest,
    PlatformScheduledTask,
    PlatformScheduleFilter,
    PlatformScheduleType,
    PlatformScheduleUpdateStatusRequest,
    ScheduledTaskStatus,
)
from core.scheduler.service import SchedulerService
from core.scheduler.source import get_schedule_source, reset_schedule_source

__all__ = [
    "get_schedule_source",
    "reset_schedule_source",
    "ScheduledTaskStatus",
    "PlatformScheduleType",
    "PlatformScheduleCreateRequest",
    "PlatformScheduleUpdateStatusRequest",
    "PlatformScheduleFilter",
    "PlatformScheduledTask",
    "PlatformRedisScheduleSnapshot",
    "SchedulerService",
]
