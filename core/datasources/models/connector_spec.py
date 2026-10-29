"""Таблица datasource: DatasourceConnectorSpec."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import (
    ConfigDict,
    model_validator,
)

from core.datasources.models.contracts import (
    DatasourceExecutorKind,
    DatasourceOperation,
    datasource_required,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject


class DatasourceConnectorSpec(PlatformModel):
    """Коннектор компании. Таблица ``datasource_connectors``.

    Каталог платформы — тот же класс без ``company_id`` и без сохранения.
    ``__global_model__``: чтение идёт по явной компании.
    """

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    datasource_connector_id: str = DbField(default="", db_pk=True)

    class Meta:
        is_table: bool = True
        table_name: str = "datasource_connectors"
        indexes: list[Index] = [Index(("company_id", "connector_id"), unique=True)]

    connector_id: str = DbField(min_length=1, max_length=255)
    name: str = DbField(min_length=1, max_length=255)
    description: str = DbField(db_type="TEXT")
    executor: DatasourceExecutorKind = DbField(max_length=32)
    icon: str = DbField(default="database", max_length=64)
    credential_schema: JsonObject = DbField(db_type="JSONB")
    operations: list[DatasourceOperation] = DbField(min_length=1, db_type="JSONB")
    mcp_server_id: str | None = DbField(default=None, max_length=255)
    mcp_introspect_tool: str | None = DbField(default=None, max_length=255)
    mcp_query_tool: str | None = DbField(default=None, max_length=255)
    mcp_execute_tool: str | None = DbField(default=None, max_length=255)
    flow_id: str | None = DbField(default=None, max_length=255)
    flow_branch_id: str = DbField(default="default", max_length=255)
    company_id: str | None = DbField(default=None, db_index=True, max_length=255)
    owner_user_id: str | None = DbField(default=None, max_length=255)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.company_id is None or self.company_id == "" or self.connector_id == "":
            raise ValueError("company_id and connector_id are required")
        if self.owner_user_id is None or self.owner_user_id == "":
            raise ValueError("owner_user_id is required")
        self.datasource_connector_id = f"{self.company_id}:{self.connector_id}"
        self.updated_at = datetime.now(timezone.utc)

    @model_validator(mode="after")
    def validate_executor_binding(self) -> DatasourceConnectorSpec:
        if self.executor == DatasourceExecutorKind.MCP:
            if self.mcp_server_id is None or not self.mcp_server_id.strip():
                raise ValueError("mcp connector requires mcp_server_id")
            if self.mcp_query_tool is None or not self.mcp_query_tool.strip():
                raise ValueError("mcp connector requires mcp_query_tool")
        if self.executor == DatasourceExecutorKind.FLOW:
            if self.flow_id is None or not self.flow_id.strip():
                raise ValueError("flow connector requires flow_id")
        if self.executor == DatasourceExecutorKind.PLATFORM:
            if self.mcp_server_id is not None or self.flow_id is not None:
                raise ValueError("platform connector cannot bind mcp_server_id or flow_id")
        return self


    @classmethod
    async def by_connector_id(cls, company_id: str, connector_id: str) -> Self | None:
        return await cls.objects.filter(
            company_id=datasource_required(company_id, "company_id"),
            connector_id=datasource_required(connector_id, "connector_id"),
        ).get_or_none()

    @classmethod
    async def list_stamped_for_company_by_name_and_connector_id_asc(cls, company_id: str) -> list[Self]:
        """Коннекторы компании, ORDER BY name ASC, connector_id ASC. Предела нет. Пустой company_id — ValueError."""
        return await cls.objects.filter(
            company_id=datasource_required(company_id, "company_id"),
        ).order_by("name", "connector_id").all()

    @classmethod
    async def upsert_by_connector_id(
        cls,
        company_id: str,
        spec: Self,
        *,
        owner_user_id: str,
    ) -> Self:
        company_id = datasource_required(company_id, "company_id")
        owner_user_id = datasource_required(owner_user_id, "owner_user_id")
        existing = await cls.objects.filter(
            company_id=company_id,
            connector_id=spec.connector_id,
        ).get_or_none()
        now = datetime.now(timezone.utc)
        if existing is None:
            created = spec.model_copy(
                update={
                    "company_id": company_id,
                    "owner_user_id": owner_user_id,
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return await cls.objects.create(instance=created)
        existing.name = spec.name
        existing.description = spec.description
        existing.executor = spec.executor
        existing.icon = spec.icon
        existing.credential_schema = spec.credential_schema
        existing.operations = spec.operations
        existing.mcp_server_id = spec.mcp_server_id
        existing.mcp_introspect_tool = spec.mcp_introspect_tool
        existing.mcp_query_tool = spec.mcp_query_tool
        existing.mcp_execute_tool = spec.mcp_execute_tool
        existing.flow_id = spec.flow_id
        existing.flow_branch_id = spec.flow_branch_id
        existing.updated_at = now
        _ = await existing.save()
        return existing
