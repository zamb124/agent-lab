"""Маршрут записи: FileSourceKind компании → storage_id. Пустой род — дефолт компании."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self

from oxyde import Field as DbField

from core.files.create_spec import FileSourceKind
from core.files.object_storage import DEFAULT_ROUTE_KIND
from core.models.platform_model import PlatformModel


def storage_route_id(company_id: str, source_kind: FileSourceKind | None) -> str:
    kind = source_kind.value if source_kind is not None else DEFAULT_ROUTE_KIND
    return f"{company_id}:{kind}"


class StorageRoute(PlatformModel):
    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True

    storage_route_id: str = DbField(db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "storage_routes"
        unique_together: list[tuple[str, str]] = [("company_id", "source_kind")]

    company_id: str = DbField(db_index=True)
    source_kind: str = DbField(default=DEFAULT_ROUTE_KIND, db_index=True)
    storage_id: str = DbField(db_index=True)
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @classmethod
    async def for_kind(cls, company_id: str, source_kind: FileSourceKind | None) -> Self | None:
        return await cls.get(storage_route_id(company_id, source_kind))

    @classmethod
    async def list_by_source_kind(cls, company_id: str) -> list[Self]:
        """Все маршруты компании, ORDER BY source_kind. Предела нет."""
        return await cls.objects.filter(company_id=company_id).order_by("source_kind").all()

    @classmethod
    async def list_unordered_for_storage(cls, storage_id: str) -> list[Self]:
        """Все маршруты хранилища. Порядка и limit нет."""
        return await cls.objects.filter(storage_id=storage_id).all()
