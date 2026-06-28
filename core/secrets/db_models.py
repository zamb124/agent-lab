"""
SQLAlchemy модели БД `platform_secrets`.

Все переменные изолированы по `company_id` и версионируются:
- `secret_variables` — актуальная версия переменной;
- `secret_variable_versions` — append-only история версий.

Значение переменной хранится единообразно как payload (base + scoped overrides):
- несекретная переменная — plaintext JSONB в `value_payload`;
- секретная — Fernet-ciphertext всего payload в `value_encrypted` (а `value_payload` пуст).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import override

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.db.models import Base
from core.types import JsonArray, JsonObject


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SecretVariableRow(Base):
    __tablename__: str = "secret_variables"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    variable_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shared_for_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    groups: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    value_payload: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    value_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    __table_args__: tuple[Index, ...] = (
        Index("ix_secret_variables_company", "company_id"),
    )

    @override
    def __repr__(self) -> str:
        return f"<SecretVariableRow(company_id='{self.company_id}', variable_key='{self.variable_key}', v={self.version})>"


class SecretVariableVersionRow(Base):
    __tablename__: str = "secret_variable_versions"

    company_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    variable_key: Mapped[str] = mapped_column(String(255), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    shared_for_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    order_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    groups: Mapped[JsonArray] = mapped_column(JSONB, nullable=False, default=list)
    value_payload: Mapped[JsonObject | None] = mapped_column(JSONB, nullable=True)
    value_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__: tuple[Index, ...] = (
        Index("ix_secret_variable_versions_company", "company_id"),
    )
