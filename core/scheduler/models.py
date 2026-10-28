"""Модели для платформенного scheduler."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import Field, field_validator, model_validator

from core.models import FlexibleBaseModel
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class PlatformScheduleType(str, Enum):
    """Тип расписания в платформенном API."""

    CRON = "cron"
    INTERVAL = "interval"
    ONE_TIME = "one_time"


class ContentType(str, Enum):
    """Тип контента задачи."""
    MESSAGE = "message"
    TOOL_CALL = "tool_call"


class ScheduledTaskStatus(str, Enum):
    """Статус scheduled task."""
    PENDING = "pending"
    PAUSED = "paused"
    EXECUTED = "executed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ScheduledTaskInfo(FlexibleBaseModel):
    """Информация о scheduled task для ExecutionState."""

    schedule_task_id: str = Field(..., description="ID записи платформенного scheduler")
    schedule_id: str | None = Field(default=None, description="ID в RedisScheduleSource")
    flow_id: str = Field(..., description="ID агента")
    session_id: str = Field(..., description="ID сессии")
    user_id: str = Field(..., description="ID пользователя")

    schedule_type: PlatformScheduleType = Field(..., description="Тип расписания")
    content_type: ContentType = Field(..., description="Тип контента")

    # Конфигурация расписания
    cron: str | None = Field(default=None, description="Cron выражение")
    interval_minutes: int | None = Field(default=None, description="Интервал в минутах")
    run_at: datetime | None = Field(default=None, description="Время запуска (one_time)")

    # Контент
    content: str = Field(..., description="Сообщение или имя tool")
    tool_args: JsonObject | None = Field(default=None, description="Аргументы для tool_call")
    description: str | None = Field(default=None, description="Описание задачи")

    status: ScheduledTaskStatus = Field(default=ScheduledTaskStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: datetime | None = Field(default=None)
    next_run: datetime | None = Field(default=None, description="Следующий запуск")
    error_message: str | None = Field(default=None, description="Сообщение об ошибке при FAILED")


class PlatformScheduleCreateRequest(FlexibleBaseModel):
    """Запрос на создание расписания."""

    target_service: str = Field(..., min_length=1, description="Сервис-назначение task")
    task_name: str = Field(..., min_length=1, description="Полное имя taskiq task")
    queue_name: str | None = Field(default=None, description="Очередь broker (если нужна)")
    schedule_type: PlatformScheduleType = Field(..., description="Тип расписания")
    cron: str | None = Field(default=None, description="Cron expression")
    interval_seconds: int | None = Field(default=None, ge=1, description="Интервал в секундах")
    run_at: datetime | None = Field(default=None, description="Время запуска для one-time")
    timezone: str = Field(default="UTC", min_length=1)
    payload: JsonObject = Field(default_factory=dict, description="kwargs для задачи")

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "PlatformScheduleCreateRequest":
        if self.schedule_type == PlatformScheduleType.CRON:
            if not self.cron:
                raise ValueError("cron is required for schedule_type=cron")
            return self
        if self.schedule_type == PlatformScheduleType.INTERVAL:
            if self.interval_seconds is None:
                raise ValueError("interval_seconds is required for schedule_type=interval")
            return self
        if self.run_at is None:
            raise ValueError("run_at is required for schedule_type=one_time")
        return self

    @field_validator("run_at")
    @classmethod
    def validate_run_at_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("run_at must be timezone-aware")
        return value


class PlatformScheduleUpdateStatusRequest(FlexibleBaseModel):
    """Запрос на смену состояния расписания."""

    reason: str | None = Field(default=None, description="Причина операции")


class PlatformScheduleFilter(FlexibleBaseModel):
    """Фильтры списка расписаний."""

    status: ScheduledTaskStatus | None = Field(default=None)
    target_service: str | None = Field(default=None)
    task_name: str | None = Field(default=None)
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class PlatformScheduledTask(PlatformModel):
    """Расписание. Таблица ``scheduler_tasks`` в ``platform_shared``.

    ``__global_model__``: сборка мусора читает ``schedule_id`` всех компаний.
    Методы одной компании фильтруют ``company_id``.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    schedule_task_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "scheduler_tasks"
        indexes: list[Index] = [
            Index(("company_id", "status")),
            Index(("company_id", "target_service")),
            Index(("company_id", "task_name")),
            Index(("company_id", "next_run_at")),
        ]

    company_id: str = DbField(db_index=True, max_length=255)
    schedule_id: str | None = DbField(default=None, db_index=True, max_length=255)
    target_service: str = DbField(db_index=True, max_length=64)
    task_name: str = DbField(db_index=True, max_length=255)
    queue_name: str | None = DbField(default=None, max_length=128)
    schedule_type: PlatformScheduleType = DbField(db_index=True, max_length=32)
    cron: str | None = DbField(default=None, max_length=128)
    interval_seconds: int | None = DbField(default=None)
    run_at: datetime | None = DbField(default=None)
    timezone: str = DbField(default="UTC", max_length=64)
    payload: JsonObject = DbField(default_factory=dict, db_type="JSONB")
    status: ScheduledTaskStatus = DbField(default=ScheduledTaskStatus.PENDING, db_index=True, max_length=32)
    created_by_user_id: str | None = DbField(default=None, db_index=True, max_length=255)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    last_run_at: datetime | None = DbField(default=None)
    next_run_at: datetime | None = DbField(default=None, db_index=True)
    error_message: str | None = DbField(default=None, db_type="TEXT")

    @field_validator("run_at", "created_at", "updated_at", "last_run_at", "next_run_at", mode="after")
    @classmethod
    def _bind_utc(cls, value: datetime | None) -> datetime | None:
        """Колонки timestamp без зоны хранят UTC: строка базы читается без tzinfo."""
        if value is None or value.tzinfo is not None:
            return value
        return value.replace(tzinfo=timezone.utc)

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.schedule_task_id == "" or self.company_id == "":
            raise ValueError("schedule_task_id and company_id are required")
        self.updated_at = datetime.now(timezone.utc)

    def next_run_for_interval(self) -> datetime:
        if self.interval_seconds is None:
            raise ValueError("interval_seconds is required for interval schedules")
        return datetime.now(timezone.utc) + timedelta(seconds=self.interval_seconds)

    @classmethod
    async def upsert_by_schedule_task_id(cls, task: Self) -> Self:
        existing = await cls.by_schedule_task_id(task.company_id, task.schedule_task_id)
        if existing is None:
            return await cls.objects.create(instance=task)
        _ = await task.save()
        return task

    @classmethod
    async def by_schedule_task_id(
        cls, company_id: str, schedule_task_id: str
    ) -> Self | None:
        """Строка компании по schedule_task_id. Нет строки — None. Пустые company_id и schedule_task_id — ValueError."""
        return await cls.objects.filter(
            company_id=_required_schedule_field(company_id, "company_id"),
            schedule_task_id=_required_schedule_field(schedule_task_id, "schedule_task_id"),
        ).get_or_none()

    @classmethod
    async def list_filtered_by_created_at_desc(
        cls, company_id: str, filters: PlatformScheduleFilter
    ) -> list[Self]:
        """Окно расписаний компании по PlatformScheduleFilter, ORDER BY created_at DESC. status, target_service и task_name равные None не фильтруют. limit и offset берутся из filters. Пустой company_id — ValueError."""
        return await (
            cls._filtered_schedule_tasks(company_id, filters)
            .order_by("-created_at")
            .limit(filters.limit)
            .offset(filters.offset)
            .all()
        )

    @classmethod
    async def count_filtered(cls, company_id: str, filters: PlatformScheduleFilter) -> int:
        """Число строк того же фильтра, что list_filtered_by_created_at_desc. status, target_service и task_name равные None не фильтруют. Пустой company_id — ValueError."""
        return await cls._filtered_schedule_tasks(company_id, filters).count()

    @classmethod
    async def list_all_schedule_ids(cls) -> frozenset[str]:
        rows = await cls.objects.exclude(schedule_id=None).all()
        schedule_ids: list[str] = []
        for row in rows:
            schedule_id = row.schedule_id
            if schedule_id is None or schedule_id.strip() == "":
                continue
            schedule_ids.append(schedule_id)
        return frozenset(schedule_ids)

    @classmethod
    async def update_status_schedule_runs_and_error(
        cls,
        company_id: str,
        schedule_task_id: str,
        status: ScheduledTaskStatus | str,
        *,
        schedule_id: str | None = None,
        last_run_at: datetime | None = None,
        next_run_at: datetime | None = None,
        error_message: str | None = None,
    ) -> bool:
        """Пишет status и updated_at. schedule_id, last_run_at, next_run_at и error_message пишутся только если не None. Нет строки — False."""
        task = await cls.by_schedule_task_id(company_id, schedule_task_id)
        if task is None:
            return False
        task.status = _schedule_status(status)
        if schedule_id is not None:
            task.schedule_id = schedule_id
        if last_run_at is not None:
            task.last_run_at = last_run_at
        if next_run_at is not None:
            task.next_run_at = next_run_at
        if error_message is not None:
            task.error_message = error_message
        task.updated_at = datetime.now(timezone.utc)
        _ = await task.save()
        return True

    @classmethod
    def _filtered_schedule_tasks(cls, company_id: str, filters: PlatformScheduleFilter):
        query = cls.objects.filter(
            company_id=_required_schedule_field(company_id, "company_id")
        )
        if filters.status is not None:
            query = query.filter(status=filters.status)
        if filters.target_service is not None:
            query = query.filter(target_service=filters.target_service)
        if filters.task_name is not None:
            query = query.filter(task_name=filters.task_name)
        return query


def _required_schedule_field(value: str, field_name: str) -> str:
    if value == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value


def _schedule_status(status: ScheduledTaskStatus | str) -> ScheduledTaskStatus:
    if isinstance(status, ScheduledTaskStatus):
        return status
    return ScheduledTaskStatus(status)


class PlatformRedisScheduleSnapshot(FlexibleBaseModel):
    """Снимок расписания из Redis schedule source."""

    schedule_task_id: str
    company_id: str
    schedule_id: str | None = None
    exists_in_redis: bool
    status: ScheduledTaskStatus
    task_name: str
    cron: str | None = None
    interval_seconds: int | None = None
    run_at: datetime | None = None
    taskiq_task_id: str | None = None
    kwargs: JsonObject = Field(default_factory=dict)
    labels: JsonObject = Field(default_factory=dict)
    missing_reason: str | None = None


__all__ = [
    "ContentType",
    "ScheduledTaskStatus",
    "ScheduledTaskInfo",
    "PlatformScheduleType",
    "PlatformScheduleCreateRequest",
    "PlatformScheduleUpdateStatusRequest",
    "PlatformScheduleFilter",
    "PlatformScheduledTask",
    "PlatformRedisScheduleSnapshot",
]
