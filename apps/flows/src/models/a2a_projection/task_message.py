"""Таблица проекции A2A."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from core.models.platform_model import PlatformModel
from core.types import JsonObject


class A2ATaskMessage(PlatformModel):
    """Сообщение истории Task. Таблица ``a2a_task_messages``."""

    __database_alias__: ClassVar[str | None] = "flows"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "a2a_task_messages"
        unique_together: list[tuple[str, str]] = [
            ("task_id", "message_id"),
            ("task_id", "ordinal"),
        ]
        indexes: list[Index] = [
            Index(["company_id", "task_id"]),
        ]

    task_message_id: str = DbField(db_pk=True)
    company_id: str = DbField()
    task_id: str = DbField()
    message_id: str = DbField()
    ordinal: int = DbField(ge=0)
    message_json: JsonObject = DbField(db_type="JSONB")
    created_at: datetime = DbField()
