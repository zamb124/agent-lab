"""Канонические JSON Schema helpers для параметров tool/function."""

from __future__ import annotations

import copy
from collections.abc import Callable
from typing import cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsValidationError
from pydantic import BaseModel

from core.types import JsonObject, require_json_object


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
        for prop in raw_props.values():
            if isinstance(prop, dict):
                _ = prop.pop("title", None)
    return out


def pydantic_model_to_parameters_schema(model: type[BaseModel]) -> JsonObject:
    """Полная JSON Schema объекта аргументов из Pydantic BaseModel (как у OpenAI parameters)."""
    raw = require_json_object(model.model_json_schema(), f"{model.__name__}.json_schema")
    return sanitize_parameters_schema_for_llm(raw)
