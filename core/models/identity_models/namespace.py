"""Таблица идентичности."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import execute_raw
from pydantic import Field, model_validator

from core.models.identity_models.contracts import (
    NamespaceCRMSettings,
    NamespaceKind,
    NamespaceSyncSettings,
)
from core.models.platform_model import CompanyScopedModel
from core.types import require_json_object


class Namespace(CompanyScopedModel):
    """Пространство компании. Таблица ``namespaces`` в ``platform_shared``.

    Внутри компании пространство адресуется ``name``. Первичный ключ строки —
    ``namespace_id`` = ``company_id:name``, чтобы ``default`` мог быть у каждой компании.
    """

    __database_alias__: ClassVar[str | None] = "shared"

    namespace_id: str = DbField(default="", db_pk=True)
    name: str = DbField(
        db_index=True,
        title="Название",
        description="Имя namespace (например 'default', 'sales')",
    )
    company_id: str = DbField(db_index=True, title="ID компании", description="ID компании-владельца")

    class Meta:
        is_table: bool = True
        table_name: str = "namespaces"
        unique_together: list[tuple[str, str]] = [("company_id", "name")]

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        self.namespace_id = f"{self.company_id}:{self.name}"
    description: str | None = Field(
        default=None, title="Описание", description="Описание namespace"
    )
    is_default: bool = Field(
        default=False,
        title="По умолчанию",
        description="Является ли namespace дефолтным для компании",
    )
    kind: NamespaceKind = Field(
        default=NamespaceKind.COMPANY_WORKSPACE,
        title="Вид",
        description="company_workspace | personal | technical",
    )
    owner_user_id: str | None = Field(
        default=None,
        title="Владелец",
        description="user_id владельца; обязателен для kind=personal",
    )
    crm_settings: NamespaceCRMSettings | None = DbField(
        default=None,
        db_type="JSONB",
        title="Настройки CRM",
        description="Опционально: UI заметок и значения по умолчанию",
    )
    sync_settings: NamespaceSyncSettings | None = DbField(
        default=None,
        db_type="JSONB",
        title="Настройки Sync",
        description="Опционально: дефолты транскрипции и речи в ленту для каналов пространства",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Создан",
        description="Время создания namespace",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        title="Обновлен",
        description="Время последнего обновления namespace",
    )

    @model_validator(mode="after")
    def _validate_personal_owner(self) -> "Namespace":
        if self.kind == NamespaceKind.PERSONAL:
            if self.owner_user_id is None or self.owner_user_id.strip() == "":
                raise ValueError("owner_user_id is required for kind=personal")
            if self.is_default:
                raise ValueError("personal namespace cannot be is_default")
        elif self.owner_user_id is not None:
            raise ValueError("owner_user_id is only allowed for kind=personal")
        return self

    @classmethod
    async def by_name(cls, name: str) -> Self | None:
        return await cls.objects.filter(name=name).get_or_none()

    @classmethod
    async def delete_by_name(cls, name: str) -> bool:
        deleted = await cls.objects.filter(name=name).delete()
        return deleted > 0

    @classmethod
    async def list_by_kind(
        cls,
        kinds: list[NamespaceKind],
        *,
        limit: int,
        offset: int,
    ) -> list[Self]:
        return await (
            cls.objects.filter(kind__in=kinds)
            .order_by("name")
            .limit(limit)
            .offset(offset)
            .all()
        )

    @classmethod
    async def count_by_kind(cls, kinds: list[NamespaceKind]) -> int:
        return await cls.objects.filter(kind__in=kinds).count()

    @classmethod
    async def partial_company_rows_by_namespace_id(cls, *, limit: int | None) -> list[Self]:
        """Строки с company_id, только name, company_id, kind и owner_user_id, ORDER BY namespace_id. limit is None не ограничивает."""
        # Менеджер отрезал бы одну компанию — сырой запрос обходит scope.
        sql = (
            "SELECT name, company_id, kind, owner_user_id "
            "FROM namespaces "
            "WHERE company_id IS NOT NULL "
            "ORDER BY namespace_id"
        )
        params: list[int] = []
        if limit is not None:
            sql = f"{sql} LIMIT $1"
            params = [limit]
        rows = await execute_raw(sql, params, using="shared")
        namespaces: list[Self] = []
        for row in rows:
            parsed = require_json_object(row, "namespace")
            name = parsed["name"]
            company_id = parsed["company_id"]
            if not isinstance(name, str) or name == "":
                raise ValueError("namespaces.name is required")
            if not isinstance(company_id, str) or company_id == "":
                raise ValueError("namespaces.company_id is required")
            kind = NamespaceKind.COMPANY_WORKSPACE
            kind_cell = parsed["kind"]
            if kind_cell == NamespaceKind.PERSONAL.value:
                kind = NamespaceKind.PERSONAL
            elif kind_cell == NamespaceKind.TECHNICAL.value:
                kind = NamespaceKind.TECHNICAL
            owner_user_id: str | None = None
            owner_cell = parsed["owner_user_id"]
            if isinstance(owner_cell, str) and owner_cell.strip() != "":
                owner_user_id = owner_cell.strip()
            if kind == NamespaceKind.PERSONAL and owner_user_id is None:
                raise ValueError(
                    f"personal namespace {name} missing owner_user_id for backfill"
                )
            if kind != NamespaceKind.PERSONAL:
                owner_user_id = None
            namespaces.append(
                cls.model_validate(
                    {
                        "name": name,
                        "company_id": company_id,
                        "kind": kind,
                        "owner_user_id": owner_user_id,
                    }
                )
            )
        return namespaces
