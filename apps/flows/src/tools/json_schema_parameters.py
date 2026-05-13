"""
Единый формат схемы параметров тула для LLM: подмножество JSON Schema (type: object + properties + required).

Используется в CodeTool.parameters и в OpenAI function calling. Источники: Pydantic-модель,
legacy Dict[str, CallParameter] или готовый dict в ToolReference.parameters_schema.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from apps.flows.src.models.tool_reference import CallParameter


def validate_tool_args_against_parameters_schema(
    *,
    schema: Dict[str, Any],
    arguments: Dict[str, Any],
) -> None:
    """
    Строгая проверка аргументов CodeTool против JSON Schema (как у LLM-провайдера).
    Совпадает с FunctionTool (Pydantic), чтобы пустые/нетипичные tool_calls давали понятную ошибку.
    """

    # jsonschema транзитивная зависимость (через FastAPI/OpenAPI pipeline).
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError as JsValidationError

    if not isinstance(schema, dict):
        raise ValueError("parameters_schema must be a dict")

    try:
        Draft202012Validator(schema).validate(arguments)
    except JsValidationError as exc:
        path = ".".join(str(p) for p in exc.path) if exc.path else ""
        msg = f"{exc.message}"
        if path:
            msg = f"{path}: {msg}"
        raise ValueError(f"Tool arguments failed JSON Schema validation ({msg})") from exc


def sanitize_parameters_schema_for_llm(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Убирает служебные title из корня и свойств — меньше шума для провайдера."""
    out = copy.deepcopy(schema)
    out.pop("title", None)
    props = out.get("properties")
    if isinstance(props, dict):
        for prop in props.values():
            if isinstance(prop, dict):
                prop.pop("title", None)
    return out


def pydantic_model_to_parameters_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Полная JSON Schema объекта аргументов из Pydantic BaseModel (как у OpenAI parameters)."""
    raw = model.model_json_schema()
    return sanitize_parameters_schema_for_llm(raw)


def call_parameters_to_parameters_schema(
    args_schema: Dict[str, CallParameter],
) -> Dict[str, Any]:
    """Собирает JSON Schema из legacy CallParameter (только type, description, required)."""
    properties: Dict[str, Any] = {}
    required: list[str] = []
    for name, p in args_schema.items():
        entry: Dict[str, Any] = {
            "type": p.type,
            "description": p.description,
        }
        properties[name] = entry
        if p.required:
            required.append(name)
    return {"type": "object", "properties": properties, "required": required}


def resolve_tool_parameters_schema(
    *,
    parameters_schema: Optional[Dict[str, Any]],
    args_schema: Optional[Dict[str, CallParameter]],
) -> Dict[str, Any]:
    """
    Итоговая схема для LLM: приоритет у parameters_schema, иначе сборка из args_schema.
    """
    if parameters_schema and isinstance(parameters_schema, dict):
        if parameters_schema.get("type") == "object" and "properties" in parameters_schema:
            return copy.deepcopy(parameters_schema)
    if args_schema:
        return call_parameters_to_parameters_schema(dict(args_schema))
    return {"type": "object", "properties": {}, "required": []}
