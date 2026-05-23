"""
Единый формат схемы параметров тула для LLM: подмножество JSON Schema (type: object + properties + required).

Используется в CodeTool.parameters и в OpenAI function calling. Источники: Pydantic-модель,
legacy Dict[str, CallParameter] или готовый dict в ToolReference.parameters_schema.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsValidationError
from pydantic import BaseModel

from core.types import JsonObject, JsonValue, require_json_object


class CallParameterLike(Protocol):
    type: str
    description: str
    required: bool


def validate_tool_args_against_parameters_schema(
    *,
    schema: JsonObject,
    arguments: JsonObject,
) -> None:
    """
    Строгая проверка аргументов CodeTool против JSON Schema (как у LLM-провайдера).
    Совпадает с FunctionTool (Pydantic), чтобы пустые/нетипичные tool_calls давали понятную ошибку.
    """

    try:
        validator = Draft202012Validator(schema)
        validate = cast(Callable[[JsonObject], None], validator.validate)
        validate(arguments)
    except JsValidationError as exc:
        path = ".".join(str(p) for p in exc.path) if exc.path else ""
        msg = f"{exc.message}"
        if path:
            msg = f"{path}: {msg}"
        raise ValueError(f"Tool arguments failed JSON Schema validation ({msg})") from exc


def sanitize_parameters_schema_for_llm(schema: JsonObject) -> JsonObject:
    """Убирает служебные title из корня и свойств — меньше шума для провайдера."""
    out = require_json_object(copy.deepcopy(schema), "parameters_schema")
    _ = out.pop("title", None)
    raw_props = out.get("properties")
    if isinstance(raw_props, dict):
        props = cast(dict[str, JsonValue], raw_props)
        for prop in props.values():
            if isinstance(prop, dict):
                _ = prop.pop("title", None)
    return out


def pydantic_model_to_parameters_schema(model: type[BaseModel]) -> JsonObject:
    """Полная JSON Schema объекта аргументов из Pydantic BaseModel (как у OpenAI parameters)."""
    raw = require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")
    return sanitize_parameters_schema_for_llm(raw)


def call_parameters_to_parameters_schema(
    args_schema: Mapping[str, CallParameterLike],
) -> JsonObject:
    """Собирает JSON Schema из legacy CallParameter (только type, description, required)."""
    properties: JsonObject = {}
    required: list[JsonValue] = []
    for name, p in args_schema.items():
        entry: JsonObject = {
            "type": p.type,
            "description": p.description,
        }
        properties[name] = entry
        if p.required:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def resolve_tool_parameters_schema(
    *,
    parameters_schema: JsonObject | None,
    args_schema: Mapping[str, CallParameterLike] | None,
) -> JsonObject:
    """
    Итоговая схема для LLM: приоритет у parameters_schema, иначе сборка из args_schema.
    """
    if parameters_schema:
        if parameters_schema.get("type") == "object" and "properties" in parameters_schema:
            return require_json_object(copy.deepcopy(parameters_schema), "parameters_schema")
    if args_schema:
        return call_parameters_to_parameters_schema(dict(args_schema))
    return {"type": "object", "properties": {}, "required": []}
