"""
SQLAlchemy модели БД `platform_worktracker` (ядро задач WorkItem).

Все таблицы изолированы по `company_id`. Union-поля доменной модели
(`created_by`, `assignment`, `hooks`, `resolution`, `links`) хранятся
как JSONB и валидируются строгими Pydantic-моделями в репозитории.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import override

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonArray, JsonObject


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkItemRow(Base):
    __tablename__: str = "work_items"

    work_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="generic")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="open", index=True)
    board_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    board_column_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    labels: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    assignment: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    blocking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hooks: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    resolution: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    links: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    variables: Mapped[JsonObject] = mapped_column(JSONB, nullable=False, default=dict)
    attachments: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[Index, ...] = (
        Index("ix_work_items_company", "company_id"),
        Index("ix_work_items_company_state", "company_id", "state"),
        Index("ix_work_items_company_board", "company_id", "board_id"),
        Index("ix_work_items_company_namespace", "company_id", "namespace"),
    )

    @override
    def __repr__(self) -> str:
        return f"<WorkItemRow(work_item_id='{self.work_item_id}', state='{self.state}')>"


class WorkQueueRow(Base):
    __tablename__: str = "work_queues"

    work_queue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[object, ...] = (
        UniqueConstraint("company_id", "slug", name="uq_work_queues_company_slug"),
        Index("ix_work_queues_company", "company_id"),
    )


class WorkQueueMemberRow(Base):
    """Участник очереди: пользователь (member_kind=user, member_ref=user_id) или
    агент (member_kind=agent, member_ref=flow_id)."""

    __tablename__: str = "work_queue_members"

    work_queue_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    member_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    member_ref: Mapped[str] = mapped_column(String(100), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="member")

    __table_args__: tuple[Index, ...] = (
        Index("ix_work_queue_members_company", "company_id"),
        Index("ix_work_queue_members_ref", "member_kind", "member_ref"),
    )


class BoardRow(Base):
    __tablename__: str = "work_boards"

    board_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    namespace: Mapped[str | None] = mapped_column(String(100), nullable=True)
    board_key: Mapped[str] = mapped_column(String(120), nullable=False, default="generic")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    columns: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[Index, ...] = (
        Index("ix_work_boards_company", "company_id"),
        Index("ix_work_boards_company_namespace", "company_id", "namespace"),
    )


class WorkItemCommentRow(Base):
    __tablename__: str = "work_item_comments"

    comment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    work_item_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    company_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    author: Mapped[JsonObject] = mapped_column(JSONB, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="system")
    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    files: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__: tuple[Index, ...] = (
        Index("ix_work_item_comments_work_item", "work_item_id"),
        Index("ix_work_item_comments_company", "company_id"),
    )
