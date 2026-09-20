"""Строка лога bus: канонический PlatformEvent + состояние обработки."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.realtime.models import BusProcessingState
from core.types import JsonObject, JsonValue


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PlatformEventLogRow(Base):
    __tablename__: str = "platform_event_log"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[JsonValue] = mapped_column(JSONB, nullable=True)
    meta: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    delivery: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    processing_state: Mapped[str] = mapped_column(String(32), nullable=False)
    owner_service: Mapped[str | None] = mapped_column(String(64), nullable=True)
    causation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[object, ...] = (
        Index("ix_platform_event_log_type", "type"),
        Index("ix_platform_event_log_causation", "causation_id"),
        Index("ix_platform_event_log_deadline", "deadline_at", "processing_state"),
        Index("ix_platform_event_log_company_created", "company_id", "created_at"),
    )


_ = BusProcessingState
