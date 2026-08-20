"""Builtin tools: live company datasources (datasource_id)."""

from __future__ import annotations

from pydantic import BaseModel

from apps.flows.src.tools.decorator import tool
from apps.flows.tools.tool_access import STANDARD_USER_TOOL_GROUPS
from core.clients.datasource_client import DatasourceClient
from core.datasources.models import DatasourceSchemaArgs, DatasourceSqlCallArgs
from core.state import ExecutionState
from core.types import JsonObject, require_json_object

_TAGS = ["datasources"]
_PERM = list(STANDARD_USER_TOOL_GROUPS)


def _dump(payload: BaseModel, label: str) -> JsonObject:
    return require_json_object(payload.model_dump(mode="json"), label)


def _client() -> DatasourceClient:
    return DatasourceClient()


@tool(
    name="db_schema",
    description=(
        "Reads schema (tables and columns) of a company datasource_id. "
        "Does not run user SQL. Tag datasources — not tables (SQLite file_id)."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=DatasourceSchemaArgs,
    effects=["read"],
)
async def db_schema(datasource_id: str, *, state: ExecutionState) -> JsonObject:
    _ = state
    snapshot = await _client().introspect(datasource_id)
    return _dump(snapshot, "db_schema.result")


@tool(
    name="db_query",
    description=(
        "Runs one SELECT/WITH on a company datasource_id with named :params. "
        "Mutating SQL is rejected; use db_execute."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=DatasourceSqlCallArgs,
    effects=["read"],
)
async def db_query(
    datasource_id: str,
    sql: str,
    params: JsonObject,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    result = await _client().query(datasource_id, sql, params)
    return _dump(result, "db_query.result")


@tool(
    name="db_execute",
    description=(
        "Runs one INSERT/UPDATE/DELETE on a company datasource_id with named :params. "
        "SELECT is rejected; use db_query. Requires approval."
    ),
    tags=_TAGS,
    permission=_PERM,
    parameters_model=DatasourceSqlCallArgs,
    effects=["write"],
    confirmation_floor="approval",
)
async def db_execute(
    datasource_id: str,
    sql: str,
    params: JsonObject,
    *,
    state: ExecutionState,
) -> JsonObject:
    _ = state
    result = await _client().execute(datasource_id, sql, params)
    return _dump(result, "db_execute.result")
