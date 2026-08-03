"""OpenAI strict parameters compiler."""

from __future__ import annotations

from apps.flows.src.tools.provider_schema import compile_openai_strict_parameters
from core.types import JsonObject, require_json_object


def test_compile_openai_strict_parameters_makes_all_properties_required() -> None:
    canonical: JsonObject = {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "required_field": {"type": "string", "description": "Required."},
            "optional_field": {"type": "integer", "description": "Optional."},
        },
        "required": ["required_field"],
    }
    compiled = compile_openai_strict_parameters(canonical)
    assert compiled["additionalProperties"] is False
    assert compiled["required"] == ["optional_field", "required_field"]
    properties = require_json_object(compiled["properties"], "compiled.properties")
    optional_field = require_json_object(properties["optional_field"], "optional_field")
    assert optional_field["type"] == ["integer", "null"]
    required_field = require_json_object(properties["required_field"], "required_field")
    assert required_field["type"] == "string"
