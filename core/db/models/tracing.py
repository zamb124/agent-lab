"""
Модели БД platform_tracing (только spans).

Shared БД не содержит таблиц трейсинга.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models.base import Base


class Spans(Base):
    """
    OpenTelemetry spans для аналитики и биллинга.

    Колонки company_id, namespace, service_name — конверт тенанта для фильтров и отчётов.
    """

    __tablename__ = "spans"

    span_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    trace_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    parent_span_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    operation_name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    status_message: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    service_name: Mapped[str] = mapped_column(String, nullable=False, index=True)
    company_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    namespace: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    user_groups: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    session_auth: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    session_agent: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    channel: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    event_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    attributes: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)
    events: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index(
            "ix_spans_company_resource_time",
            "company_id",
            "resource_type",
            "resource_id",
            "start_time",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Spans(span_id={self.span_id!r}, trace_id={self.trace_id!r}, "
            f"operation_name={self.operation_name!r})>"
        )
