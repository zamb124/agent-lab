"""Запрос на доступ к сущности CRM."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar, Self

from oxyde import Field as DbField
from oxyde import Index, Query, atomic

from core.models.platform_model import PlatformModel


class AccessRequest(PlatformModel):
    """Строка ``access_requests``. Колонка ключа в базе — ``request_id``."""

    __database_alias__: ClassVar[str | None] = "crm"
    __global_model__: ClassVar[bool] = True

    class Meta:
        is_table: bool = True
        table_name: str = "access_requests"
        indexes: list[Index] = [
            Index(["owner_id", "status"]),
            Index(["resource_type", "resource_id"]),
        ]

    access_request_id: str = DbField(db_pk=True, db_column="request_id", max_length=100)
    company_id: str = DbField(max_length=100, db_index=True)
    requester_id: str = DbField(max_length=100, db_index=True)
    requester_company_id: str = DbField(max_length=100, db_index=True)
    owner_id: str = DbField(max_length=100, db_index=True)
    resource_type: str = DbField(max_length=50)
    resource_id: str = DbField(max_length=100, db_index=True)
    created_at: datetime = DbField()
    updated_at: datetime = DbField()
    message: str | None = DbField(default=None, db_type="TEXT")
    status: str = DbField(default="pending", max_length=20)
    include_dependencies: bool = DbField(default=False)
    max_depth: int = DbField(default=1)
    created_entity_id: str | None = DbField(default=None, max_length=100)

    @classmethod
    async def create(cls, access_request: Self) -> Self:
        return await cls.objects.create(instance=access_request)

    @classmethod
    def query_by_status_in_company(cls, company_id: str, status: str | None) -> Query[Self]:
        """Запрос заявок компании. status is None и пустая строка не фильтруют. Порядка нет."""
        rows = cls.objects.filter(company_id=company_id)
        if status is not None and status != "":
            rows = rows.filter(status=status)
        return rows

    @classmethod
    async def delete_duplicate_pending_for_entity(cls, entity_id: str) -> None:
        """Удаляет повторные pending-заявки на сущность. Для пары (requester_id, resource_id) оставляет самую раннюю по created_at. Если удаление задело не одну строку — ValueError."""
        pending = await cls.objects.filter(
            resource_type="entity",
            resource_id=entity_id,
            status="pending",
        ).order_by("created_at").all()
        seen: set[tuple[str, str]] = set()
        to_delete: list[str] = []
        for request in pending:
            key = (request.requester_id, request.resource_id)
            if key not in seen:
                seen.add(key)
                continue
            to_delete.append(request.access_request_id)
        if len(to_delete) == 0:
            return
        async with atomic(using="crm"):
            for access_request_id in to_delete:
                deleted = await cls.objects.filter(
                    access_request_id=access_request_id
                ).delete()
                if deleted != 1:
                    raise ValueError(f"Access request {access_request_id} was not deleted")

    @classmethod
    async def update_entity_resource_id(
        cls,
        company_id: str,
        source_id: str,
        survivor_id: str,
    ) -> int:
        """Пишет resource_id заявок компании с resource_type entity и resource_id source_id. Возвращает число строк. Нет таких — 0."""
        return await cls.objects.filter(
            company_id=company_id,
            resource_type="entity",
            resource_id=source_id,
        ).update(using="crm", resource_id=survivor_id)
