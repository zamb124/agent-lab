"""Load/deref OpenRouter OpenAPI schemas for LLM proxy contract tests."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Final, cast

from core.types import JsonObject, require_json_object

_OPENROUTER_OPENAPI_FIXTURE: Final[Path] = (
    Path(__file__).resolve().parents[1] / "fixtures" / "openrouter.openapi.json"
)

_SCHEMA_NAMES: Final[tuple[str, ...]] = (
    "ChatRequest",
    "ChatResult",
    "ChatStreamChunk",
    "ChatUsage",
    "ChatChoice",
)


def openrouter_openapi_fixture_path() -> Path:
    return _OPENROUTER_OPENAPI_FIXTURE


@lru_cache(maxsize=1)
def load_openrouter_openapi() -> JsonObject:
    path = openrouter_openapi_fixture_path()
    if not path.is_file():
        raise FileNotFoundError(f"OpenRouter OpenAPI fixture missing: {path}")
    return require_json_object(
        json.loads(path.read_text(encoding="utf-8")),
        "openrouter.openapi",
    )


def _component_schemas(openapi: JsonObject) -> dict[str, JsonObject]:
    components = require_json_object(openapi.get("components"), "openapi.components")
    schemas_raw = components.get("schemas")
    if not isinstance(schemas_raw, dict):
        raise ValueError("openapi.components.schemas must be an object")
    schemas: dict[str, JsonObject] = {}
    for name, schema_value in schemas_raw.items():
        if not isinstance(name, str):
            raise ValueError("schema name must be a string")
        schemas[name] = require_json_object(schema_value, f"schemas.{name}")
    return schemas


def _resolve_refs(node: object, schemas: dict[str, JsonObject], *, stack: tuple[str, ...]) -> object:
    if isinstance(node, list):
        return [_resolve_refs(item, schemas, stack=stack) for item in node]
    if not isinstance(node, dict):
        return node
    node_object = cast(dict[str, object], node)
    ref = node_object.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
        schema_name = ref.removeprefix("#/components/schemas/")
        if schema_name in stack:
            # Break cycles for jsonschema (OR schemas are recursive).
            return {"type": "object"}
        if schema_name not in schemas:
            raise KeyError(f"OpenAPI schema not found: {schema_name}")
        return _resolve_refs(schemas[schema_name], schemas, stack=(*stack, schema_name))
    resolved: dict[str, object] = {}
    for key, value in node_object.items():
        resolved[key] = _resolve_refs(value, schemas, stack=stack)
    return resolved


@lru_cache(maxsize=16)
def get_openrouter_schema(schema_name: str) -> JsonObject:
    if schema_name not in _SCHEMA_NAMES:
        raise KeyError(f"schema {schema_name!r} is not in contract allowlist {_SCHEMA_NAMES}")
    openapi = load_openrouter_openapi()
    schemas = _component_schemas(openapi)
    if schema_name not in schemas:
        raise KeyError(f"OpenAPI schema missing in fixture: {schema_name}")
    resolved = _resolve_refs(schemas[schema_name], schemas, stack=(schema_name,))
    return require_json_object(resolved, f"resolved.{schema_name}")


def validate_against_openrouter_schema(schema_name: str, payload: object) -> None:
    """Raise jsonschema.ValidationError if payload does not match schema."""
    import jsonschema

    schema = get_openrouter_schema(schema_name)
    validator_cls = jsonschema.Draft202012Validator
    validator_cls.check_schema(schema)
    validator_cls(schema).validate(payload)


__all__ = [
    "get_openrouter_schema",
    "load_openrouter_openapi",
    "openrouter_openapi_fixture_path",
    "validate_against_openrouter_schema",
]
