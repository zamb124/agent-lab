"""Строка лога bus: PlatformEvent и состояние обработки. Таблица ``platform_event_log``."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Q
from oxyde.queries.select import Query

from core.events.contract import EventDelivery, PlatformEvent, PlatformEventMeta
from core.models.platform_model import PlatformModel
from core.realtime.models import BusProcessingState
from core.types import JsonObject, JsonValue


class PlatformEventLog(PlatformModel):
    """Durable-лог шины. Алиас ``realtime``, модель глобальная: событие читается по ``event_id``."""

    __database_alias__: ClassVar[str | None] = "realtime"
    __global_model__: ClassVar[bool] = True

    event_id: str = DbField(db_pk=True, max_length=64)
    type: str = DbField(db_type="TEXT")
    company_id: str = DbField(max_length=100)
    meta: JsonObject = DbField(db_type="JSONB")
    processing_state: str = DbField(max_length=32)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    payload: JsonValue = DbField(default=None, db_type="JSONB")
    delivery: JsonObject | None = DbField(default=None, db_type="JSONB")
    owner_service: str | None = DbField(default=None, max_length=64)
    causation_id: str | None = DbField(default=None, max_length=64)
    deadline_at: datetime | None = DbField(default=None)

    @classmethod
    async def create(cls, row: Self) -> Self:
        """Вставляет строку лога."""
        return await cls.objects.create(instance=row)

    @classmethod
    async def list_expired_by_deadline_at_asc(cls, *, now: datetime, limit: int) -> list[Self]:
        """Команды с deadline_at < now в received и dispatched, ORDER BY deadline_at ASC, не больше limit."""
        return await (
            cls.objects.filter(
                deadline_at__isnull=False,
                deadline_at__lt=now,
                processing_state__in=[
                    BusProcessingState.RECEIVED.value,
                    BusProcessingState.DISPATCHED.value,
                ],
            )
            .order_by("deadline_at")
            .limit(limit)
            .all()
        )

    @classmethod
    def terminal_query(cls, causation_id: str) -> Query[Self]:
        """Запрос строк causation_id с типом на _succeeded или _failed. Порядок задаёт вызывающий."""
        return cls.objects.filter(causation_id=causation_id).filter(
            Q(type__endswith="_succeeded") | Q(type__endswith="_failed")
        )

    class Meta:
        is_table: bool = True
        table_name: str = "platform_event_log"
        indexes: list[Index] = [
            Index(["type"]),
            Index(["causation_id"]),
            Index(["deadline_at", "processing_state"]),
            Index(["company_id", "created_at"]),
        ]

    def platform_event(self) -> PlatformEvent:
        delivery: EventDelivery | None = None
        if self.delivery is not None:
            delivery = EventDelivery.model_validate(self.delivery)
        return PlatformEvent(
            event_id=self.event_id,
            type=self.type,
            company_id=self.company_id,
            payload=self.payload,
            meta=PlatformEventMeta.model_validate(self.meta),
            delivery=delivery,
        )
