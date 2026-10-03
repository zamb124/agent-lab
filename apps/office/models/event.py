"""Таблицы platform_office."""

import json
import uuid
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.models.platform_model import CompanyScopedModel
from core.types import JsonObject


class OfficeDocumentEvent(CompanyScopedModel):
    """Журнал активности по документу. ``payload_json`` — JSON-текст строки."""

    __database_alias__: ClassVar[str | None] = "office"

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_events"

    event_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=128, db_index=True)
    event_type: str = DbField(max_length=64)
    user_id: str = DbField(max_length=100)
    payload_json: str = DbField(db_type="TEXT")
    created_at: datetime = DbField()

    @classmethod
    async def list_for_file(cls, file_id: str, *, limit: int) -> list[Self]:
        return await (
            cls.objects.filter(file_id=file_id)
            .order_by("-created_at")
            .limit(limit)
            .all()
        )

    @classmethod
    async def record_document_event(
        cls,
        *,
        file_id: str,
        company_id: str,
        event_type: str,
        user_id: str,
        payload: JsonObject,
    ) -> None:
        _ = await cls.objects.create(
            instance=cls(
                event_id=uuid.uuid4().hex,
                file_id=file_id,
                company_id=company_id,
                event_type=event_type,
                user_id=user_id,
                payload_json=json.dumps(payload, ensure_ascii=False),
                created_at=datetime.now(timezone.utc),
            )
        )
