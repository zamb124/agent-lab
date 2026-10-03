"""Таблица datasource: DatasourceConnection."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import (
    ConfigDict,
    SerializerFunctionWrapHandler,
    model_serializer,
)

from core.datasources.models.contracts import (
    DatasourceSqlOperation,
    DatasourceSslMode,
    datasource_required,
)
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class DatasourceConnection(PlatformModel):
    """Подключение к внешней базе. Таблица ``datasource_connections``. ``password_encrypted`` в JSON не отдаётся."""

    __database_alias__: ClassVar[str | None] = "shared"
    __global_model__: ClassVar[bool] = True
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")

    datasource_id: str = DbField(db_pk=True, max_length=255)

    class Meta:
        is_table: bool = True
        table_name: str = "datasource_connections"
        indexes: list[Index] = [
            Index(("company_id", "name"), unique=True),
            Index(("company_id", "connector_id")),
        ]

    company_id: str = DbField(db_index=True, max_length=255)
    connector_id: str = DbField(max_length=255)
    name: str = DbField(max_length=255)
    host: str | None = DbField(default=None, max_length=255)
    port: int | None = DbField(default=None, ge=1, le=65535)
    database_name: str | None = DbField(default=None, max_length=255)
    username: str | None = DbField(default=None, max_length=255)
    password_encrypted: str | None = DbField(default=None, db_type="TEXT")
    ssl_mode: DatasourceSslMode = DbField(default=DatasourceSslMode.REQUIRE, max_length=32)
    allowed_operations: list[DatasourceSqlOperation] = DbField(
        default_factory=lambda: [DatasourceSqlOperation.SELECT],
        db_type="JSONB",
    )
    statement_timeout_ms: int = DbField(default=15_000, ge=1, le=120_000)
    max_rows: int = DbField(default=1_000, ge=1, le=10_000)
    mcp_server_id: str | None = DbField(default=None, max_length=255)
    flow_id: str | None = DbField(default=None, max_length=255)
    flow_branch_id: str = DbField(default="default", max_length=255)
    owner_user_id: str = DbField(max_length=255)
    created_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = DbField(default_factory=lambda: datetime.now(timezone.utc))

    @model_serializer(mode="wrap", when_used="json")
    def _json_without_password(self, handler: SerializerFunctionWrapHandler) -> JsonObject:
        payload = require_serializer_json_object(handler, self, "DatasourceConnection")
        if "password_encrypted" in payload:
            del payload["password_encrypted"]
        return payload

    @override
    async def pre_save(self, *, is_create: bool, update_fields: set[str] | None = None) -> None:
        _ = is_create, update_fields
        if self.datasource_id == "" or self.company_id == "" or self.name == "" or self.owner_user_id == "":
            raise ValueError("datasource_id, company_id, name and owner_user_id are required")
        self.updated_at = datetime.now(timezone.utc)

    @classmethod
    async def list_for_authz(cls, *, limit: int | None) -> list[Self]:
        ordered = cls.objects.order_by("datasource_id")
        if limit is None:
            return await ordered.all()
        return await ordered.limit(limit).all()


    @classmethod
    async def list_by_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=datasource_required(company_id, "company_id"),
        ).order_by("name", "datasource_id").all()

    @classmethod
    async def insert(cls, connection: Self) -> Self:
        clash = await cls.objects.filter(
            company_id=connection.company_id,
            name=connection.name,
        ).get_or_none()
        if clash is not None:
            raise ValueError(
                f"datasource name {connection.name!r} already exists in company {connection.company_id}"
            )
        return await cls.objects.create(instance=connection)

    @classmethod
    async def update_connection(cls, connection: Self) -> Self:
        existing = await cls.get(connection.datasource_id)
        if existing is None:
            raise ValueError(f"datasource not found: {connection.datasource_id}")
        if existing.company_id != connection.company_id:
            raise ValueError("datasource_id belongs to another company")
        name_owner = await cls.objects.filter(
            company_id=connection.company_id,
            name=connection.name,
        ).get_or_none()
        if name_owner is not None and name_owner.datasource_id != connection.datasource_id:
            raise ValueError(
                f"datasource name {connection.name!r} already exists in company {connection.company_id}"
            )
        _ = await connection.save()
        return connection
