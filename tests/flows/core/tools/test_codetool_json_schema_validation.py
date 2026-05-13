"""Валидация аргументов CodeTool против parameters_schema."""

from __future__ import annotations

import pytest

from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema


def test_validate_tool_args_rejects_missing_required() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "description": {"type": "string"}},
        "required": ["name", "description"],
    }
    with pytest.raises(ValueError, match="failed JSON Schema validation"):
        validate_tool_args_against_parameters_schema(schema=schema, arguments={})


def test_validate_tool_args_accepts_valid_object() -> None:
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "mode": {"type": "string", "default": "propose"}},
        "required": ["name"],
    }
    validate_tool_args_against_parameters_schema(schema=schema, arguments={"name": "ok"})

