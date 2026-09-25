"""Доменные модели внешних баз (datasource): коннектор, подключение, протокол."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar, Self, override

from oxyde import Field as DbField
from oxyde import Index
from pydantic import (
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from core.models.base import StrictBaseModel
from core.models.platform_model import PlatformModel
from core.types import JsonObject, require_serializer_json_object


class DatasourceExecutorKind(StrEnum):
    PLATFORM = "platform"
    MCP = "mcp"
    FLOW = "flow"


class DatasourceOperation(StrEnum):
    INTROSPECT = "introspect"
    QUERY = "query"
    EXECUTE = "execute"


class DatasourceSqlOperation(StrEnum):
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"


class DatasourceSslMode(StrEnum):
    DISABLE = "disable"
    REQUIRE = "require"
    VERIFY_FULL = "verify-full"


class DatasourceColumn(StrictBaseModel):
    name: str
    data_type: str


class DatasourceTable(StrictBaseModel):
    table_name: str
    columns: list[DatasourceColumn] = Field(default_factory=list)


class DatasourceSchemaSnapshot(StrictBaseModel):
    tables: list[DatasourceTable] = Field(default_factory=list)


class DatasourceQueryResult(StrictBaseModel):
    columns: list[str] = Field(default_factory=list)
    rows: list[JsonObject] = Field(default_factory=list)
    row_count: int = Field(ge=0)
    truncated: bool = False


class DatasourceExecuteResult(StrictBaseModel):
    rowcount: int = Field(ge=0)


class DatasourceTestResult(StrictBaseModel):
    ok: bool
    latency_ms: int = Field(ge=0)
    server_version: str | None = None



def _datasource_required(value: str, field_name: str) -> str:
    if value.strip() == "":
        raise ValueError(f"{field_name} cannot be empty.")
    return value

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
            company_id=_datasource_required(company_id, "company_id"),
            connector_id=_datasource_required(connector_id, "connector_id"),
        ).get_or_none()

    @classmethod
    async def list_stamped_for_company(cls, company_id: str) -> list[Self]:
        return await cls.objects.filter(
            company_id=_datasource_required(company_id, "company_id"),
        ).order_by("name", "connector_id").all()

    @classmethod
    async def upsert_by_connector_id(
        cls,
        company_id: str,
        spec: Self,
        *,
        owner_user_id: str,
    ) -> Self:
        company_id = _datasource_required(company_id, "company_id")
        owner_user_id = _datasource_required(owner_user_id, "owner_user_id")
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
            company_id=_datasource_required(company_id, "company_id"),
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



class DatasourceConnectionCreate(StrictBaseModel):
    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_mode: DatasourceSslMode = DatasourceSslMode.REQUIRE
    allowed_operations: list[DatasourceSqlOperation] = Field(
        default_factory=lambda: [DatasourceSqlOperation.SELECT]
    )
    statement_timeout_ms: int = Field(default=15_000, ge=1, le=120_000)
    max_rows: int = Field(default=1_000, ge=1, le=10_000)
    mcp_server_id: str | None = None
    flow_id: str | None = None
    flow_branch_id: str = "default"


class DatasourceConnectionPatch(StrictBaseModel):
    name: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    database_name: str | None = None
    username: str | None = None
    password: str | None = None
    ssl_mode: DatasourceSslMode | None = None
    allowed_operations: list[DatasourceSqlOperation] | None = None
    statement_timeout_ms: int | None = Field(default=None, ge=1, le=120_000)
    max_rows: int | None = Field(default=None, ge=1, le=10_000)
    mcp_server_id: str | None = None
    flow_id: str | None = None
    flow_branch_id: str | None = None


class DatasourceConnectionPatchPayload(DatasourceConnectionPatch):
    datasource_id: str = Field(min_length=1)


class DatasourceListPayload(StrictBaseModel):
    limit: int = Field(default=200, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class DatasourceConnectorUpsert(StrictBaseModel):
    connector_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str
    executor: DatasourceExecutorKind
    icon: str = "database"
    credential_schema: JsonObject
    operations: list[DatasourceOperation] = Field(min_length=1)
    mcp_server_id: str | None = None
    mcp_introspect_tool: str | None = None
    mcp_query_tool: str | None = None
    mcp_execute_tool: str | None = None
    flow_id: str | None = None
    flow_branch_id: str = "default"


class DatasourceSchemaArgs(StrictBaseModel):
    datasource_id: str = Field(min_length=1)


class DatasourceSqlRequest(StrictBaseModel):
    sql: str = Field(min_length=1)
    params: JsonObject = Field(default_factory=dict)


class DatasourceSqlCallArgs(DatasourceSqlRequest):
    datasource_id: str = Field(min_length=1)


DatasourceProtocolResult = (
    DatasourceSchemaSnapshot | DatasourceQueryResult | DatasourceExecuteResult | DatasourceTestResult
)


__all__ = [
    "DatasourceColumn",
    "DatasourceConnection",
    "DatasourceConnectionCreate",
    "DatasourceConnectionPatch",
    "DatasourceConnectionPatchPayload",
    "DatasourceConnectorSpec",
    "DatasourceConnectorUpsert",
    "DatasourceExecuteResult",
    "DatasourceExecutorKind",
    "DatasourceListPayload",
    "DatasourceOperation",
    "DatasourceProtocolResult",
    "DatasourceQueryResult",
    "DatasourceSchemaArgs",
    "DatasourceSqlCallArgs",
    "DatasourceSqlRequest",
    "DatasourceSchemaSnapshot",
    "DatasourceSqlOperation",
    "DatasourceSslMode",
    "DatasourceTable",
    "DatasourceTestResult",
]
