"""Unit tests for structured handback validation (output_schema)."""

from __future__ import annotations

import pytest

from apps.flows.src.tools.json_schema_parameters import validate_tool_args_against_parameters_schema


class TestStructuredHandbackSchema:
    def test_output_schema_validates_handback_variables(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "ticket_id": {"type": "string"},
                "warehouse_id": {"type": "string"},
            },
            "required": ["ticket_id"],
        }
        validate_tool_args_against_parameters_schema(
            schema=schema,
            arguments={"ticket_id": "TKT-1", "warehouse_id": "WH-9"},
        )

    def test_output_schema_rejects_invalid_handback_variables(self) -> None:
        schema = {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
        }
        with pytest.raises(ValueError, match="JSON Schema validation"):
            validate_tool_args_against_parameters_schema(
                schema=schema,
                arguments={},
            )
