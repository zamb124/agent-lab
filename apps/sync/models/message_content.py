"""Таблица sync."""

from __future__ import annotations

from typing import ClassVar

from oxyde import Field as DbField
from oxyde import Index

from apps.sync.models.messages import MessageContentModel
from core.models.platform_model import PlatformModel
from core.types import JsonObject, parse_json_object, require_json_object


class SyncMessageContent(PlatformModel):
    """Строка ``sync_message_contents``, алиас ``sync``, ``__global_model__``.

    Первичный ключ в базе — ``id`` (BIGSERIAL). Поле модели — ``content_id``.
    Колонка порядка — ``order``, поле модели — ``order_index``.
    Ответ API — ``MessageContentModel``, не эта строка.
    """

    __database_alias__: ClassVar[str | None] = "sync"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "sync_message_contents"
        indexes: list[Index] = [
            Index(["message_id"]),
        ]

    message_id: str = DbField(max_length=64)
    type: str = DbField(max_length=64)
    order_index: int = DbField(db_column="order", db_type="INTEGER")
    data: JsonObject = DbField(db_type="JSONB")
    content_id: int | None = DbField(default=None, db_pk=True, db_column="id")

    @classmethod
    async def list_for_message(cls, message_id: str) -> list[MessageContentModel]:
        rows = await cls.objects.filter(message_id=message_id).order_by(
            "order_index", "content_id"
        ).all()
        return [_content_model(row) for row in rows]

def _content_model(row: SyncMessageContent) -> MessageContentModel:
    raw_data = row.data
    if isinstance(raw_data, str):
        data = parse_json_object(raw_data, "message content")
    else:
        data = require_json_object(raw_data, "message content")
    return MessageContentModel.model_validate(
        {"type": row.type, "data": data, "order": row.order_index}
    )
