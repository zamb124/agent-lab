"""Таблицы platform_office."""

import uuid
from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index as OxydeIndex
from oxyde import atomic, execute_raw

from core.models.platform_model import PlatformModel


class OfficeDocumentRevision(PlatformModel):
    """Снимок версии документа. ``file_id`` — привязка, ``revision_file_id`` — файл снимка."""

    __database_alias__: ClassVar[str | None] = "office"
    __global_model__: ClassVar[bool] = True

    revision_id: str = DbField(db_pk=True, max_length=64)
    file_id: str = DbField(max_length=128, db_index=True)
    revision_file_id: str = DbField(max_length=128)
    revision_number: int = DbField()
    created_by_user_id: str = DbField(max_length=100)
    created_at: datetime = DbField()

    class Meta:
        is_table: bool = True
        table_name: str = "office_document_revisions"
        indexes: list[OxydeIndex] = [
            OxydeIndex(["file_id", "revision_number"]),
        ]

    @classmethod
    async def list_by_revision_number_desc(cls, file_id: str, *, limit: int) -> list[Self]:
        """Ревизии файла, ORDER BY revision_number DESC, не больше limit."""
        return await (
            cls.objects.filter(file_id=file_id)
            .order_by("-revision_number")
            .limit(limit)
            .all()
        )

    @classmethod
    async def append(
        cls,
        *,
        file_id: str,
        revision_file_id: str,
        created_by_user_id: str,
    ) -> Self:
        """Добавляет следующую ревизию file_id под блокировкой. Первая — номер 1."""
        async with atomic(using="office"):
            _ = await execute_raw(
                "SELECT pg_advisory_xact_lock(hashtext($1))",
                [file_id],
                using="office",
            )
            revisions = await cls.list_by_revision_number_desc(file_id, limit=1)
            latest = revisions[0] if len(revisions) > 0 else None
            revision_number = 1 if latest is None else latest.revision_number + 1
            return await cls.objects.create(
                instance=cls(
                    revision_id=uuid.uuid4().hex,
                    file_id=file_id,
                    revision_file_id=revision_file_id,
                    revision_number=revision_number,
                    created_by_user_id=created_by_user_id,
                    created_at=datetime.now(timezone.utc),
                )
            )
