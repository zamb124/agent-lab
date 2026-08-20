"""Live datasource SDK capabilities: db.* via DatasourceClient → flows."""

from __future__ import annotations

from typing import TypeAlias

from pydantic import BaseModel, ValidationError

from core.capabilities import CAPABILITY_LANGUAGES, CapabilityDefinition
from core.clients.datasource_client import DatasourceClient
from core.clients.service_client import ServiceClientError
from core.datasources.models import DatasourceSchemaArgs, DatasourceSqlCallArgs
from core.types import JsonObject, JsonValue, require_json_object

DbArgsModel: TypeAlias = type[BaseModel]

_DB_OUTPUT_SCHEMA: JsonObject = {
    "type": "object",
    "description": "JSON from DatasourceProtocol (schema / query / execute).",
}


def _input_schema(model: DbArgsModel) -> JsonObject:
    return require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")


def _definition(
    *,
    method: str,
    title: str,
    description: str,
    args_model: DbArgsModel,
) -> CapabilityDefinition:
    return CapabilityDefinition(
        name=f"db.{method}",
        title=title,
        description=description,
        input_schema=_input_schema(args_model),
        output_schema=_DB_OUTPUT_SCHEMA,
        languages=list(CAPABILITY_LANGUAGES),
        tags=["datasources"],
        sdk_namespace="db",
        sdk_method=method,
    )


DB_CAPABILITY_SPECS: tuple[tuple[str, str, str, DbArgsModel], ...] = (
    (
        "schema",
        "Datasource schema",
        "Reads tables/columns for datasource_id. No user SQL.",
        DatasourceSchemaArgs,
    ),
    (
        "query",
        "Datasource SQL query",
        "Runs one SELECT/WITH with named :params on datasource_id.",
        DatasourceSqlCallArgs,
    ),
    (
        "execute",
        "Datasource SQL execute",
        "Runs one INSERT/UPDATE/DELETE with named :params on datasource_id.",
        DatasourceSqlCallArgs,
    ),
)


def db_capability_definitions() -> dict[str, CapabilityDefinition]:
    return {
        f"db.{method}": _definition(
            method=method,
            title=title,
            description=description,
            args_model=args_model,
        )
        for method, title, description, args_model in DB_CAPABILITY_SPECS
    }


def _dump(payload: BaseModel, label: str) -> JsonObject:
    return require_json_object(payload.model_dump(mode="json"), label)


async def invoke_db_client(method: str, kwargs: JsonObject) -> JsonValue:
    specs = {item[0]: item[3] for item in DB_CAPABILITY_SPECS}
    args_model = specs.get(method)
    if args_model is None:
        raise ValueError(f"unknown db method {method!r}")
    try:
        args = args_model.model_validate(kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc
    client = DatasourceClient()
    try:
        if method == "schema" and isinstance(args, DatasourceSchemaArgs):
            snapshot = await client.introspect(args.datasource_id)
            return _dump(snapshot, "db.schema")
        if method == "query" and isinstance(args, DatasourceSqlCallArgs):
            result = await client.query(args.datasource_id, args.sql, args.params)
            return _dump(result, "db.query")
        if method == "execute" and isinstance(args, DatasourceSqlCallArgs):
            result = await client.execute(args.datasource_id, args.sql, args.params)
            return _dump(result, "db.execute")
    except ServiceClientError as exc:
        raise ValueError(str(exc)) from exc
    raise ValueError(f"db.{method} args mismatch")
